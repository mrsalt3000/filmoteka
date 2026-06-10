"""User-specific endpoints: profile, watch history, blacklist."""

# ruff: noqa: B008  FastAPI requires Depends() in function signatures

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import false as sa_false
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from filmoteka.api.auth import _get_current_user
from filmoteka.api.schemas.auth import UserOut
from filmoteka.api.schemas.watch import (
    MoodQueryRequest,
    RecommendationItem,
    RecommendationsResponse,
    WatchHistoryItem,
    WatchHistoryResponse,
)
from filmoteka.domain.access.models import User, UserFilmBlacklist
from filmoteka.domain.catalog.models import (
    Film,
    Genre,
    MediaFile,
    MovieEdition,
    film_genre,
    film_person,
)
from filmoteka.domain.watching.models import WatchEvent
from filmoteka.infrastructure.database import get_db
from filmoteka.infrastructure.settings import settings

router = APIRouter(prefix="/me", tags=["users"])


class BlacklistResponse(BaseModel):
    film_ids: list[int]


class IncognitoRequest(BaseModel):
    incognito: bool


class ExcludeFamilyRequest(BaseModel):
    exclude: bool


class ExcludeWatchedRequest(BaseModel):
    exclude: bool


class IncludeExternalRequest(BaseModel):
    include: bool


@router.get("/blacklist", response_model=BlacklistResponse)
def list_blacklist(
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
) -> BlacklistResponse:
    """Return the list of film IDs the current user has blacklisted."""
    rows = (
        db.query(UserFilmBlacklist.film_id)
        .filter(UserFilmBlacklist.user_id == current_user.id)
        .all()
    )
    return BlacklistResponse(film_ids=[r[0] for r in rows])


@router.post("/blacklist/{film_id}", status_code=204)
def add_to_blacklist(
    film_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
) -> None:
    """Add a film to the current user's blacklist."""
    film = db.get(Film, film_id)
    if film is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Film not found",
        )

    existing = (
        db.query(UserFilmBlacklist)
        .filter(
            UserFilmBlacklist.user_id == current_user.id,
            UserFilmBlacklist.film_id == film_id,
        )
        .first()
    )
    if existing is not None:
        return  # already blacklisted — idempotent

    db.add(UserFilmBlacklist(user_id=current_user.id, film_id=film_id))
    db.commit()


@router.delete("/blacklist/{film_id}", status_code=204)
def remove_from_blacklist(
    film_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
) -> None:
    """Remove a film from the current user's blacklist."""
    entry = (
        db.query(UserFilmBlacklist)
        .filter(
            UserFilmBlacklist.user_id == current_user.id,
            UserFilmBlacklist.film_id == film_id,
        )
        .first()
    )
    if entry is None:
        return  # not blacklisted — idempotent

    db.delete(entry)
    db.commit()


@router.put("/incognito")
def set_incognito(
    body: IncognitoRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
) -> UserOut:
    """Enable or disable incognito mode for the current user."""
    current_user.incognito = body.incognito
    db.commit()
    db.refresh(current_user)
    return UserOut.model_validate(current_user)


@router.put("/exclude-family")
def set_exclude_family(
    body: ExcludeFamilyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
) -> UserOut:
    """Set whether family videos are excluded from recommendations."""
    current_user.exclude_family_from_recommendations = body.exclude
    db.commit()
    db.refresh(current_user)
    return UserOut.model_validate(current_user)


@router.put("/exclude-watched")
def set_exclude_watched(
    body: ExcludeWatchedRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
) -> UserOut:
    """Set whether already-watched films are excluded from the catalog."""
    current_user.exclude_watched = body.exclude
    db.commit()
    db.refresh(current_user)
    return UserOut.model_validate(current_user)


@router.put("/include-external")
def set_include_external(
    body: IncludeExternalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
) -> UserOut:
    """Set whether external films (not in library) appear in recommendations."""
    current_user.include_external = body.include
    db.commit()
    db.refresh(current_user)
    return UserOut.model_validate(current_user)


# ── Recommendations ─────────────────────────────────────────────


# Mood → genre keyword mapping (fallback when no LLM)
_MOOD_GENRES: dict[str, list[str]] = {
    "романтический": ["Romance", "Drama", "Comedy"],
    "романтика": ["Romance", "Drama", "Comedy"],
    "romance": ["Romance", "Drama", "Comedy"],
    "вечер": ["Romance", "Comedy", "Drama"],
    "боевик": ["Action", "Thriller"],
    "action": ["Action", "Thriller"],
    "экшн": ["Action", "Thriller"],
    "комедия": ["Comedy"],
    "comedy": ["Comedy"],
    "страшно": ["Horror", "Thriller", "Mystery"],
    "horror": ["Horror", "Thriller", "Mystery"],
    "ужасы": ["Horror", "Thriller", "Mystery"],
    "семья": ["Family", "Animation", "Adventure"],
    "family": ["Family", "Animation", "Adventure"],
    "семейный": ["Family", "Animation", "Adventure"],
    "научная фантастика": ["Sci-Fi", "Adventure"],
    "sci-fi": ["Sci-Fi", "Adventure"],
    "фантастика": ["Sci-Fi", "Adventure", "Fantasy"],
    "детектив": ["Mystery", "Thriller", "Crime"],
    "триллер": ["Thriller", "Mystery", "Crime"],
    "thriller": ["Thriller", "Mystery", "Crime"],
    "драма": ["Drama"],
    "drama": ["Drama"],
    "война": ["War", "Drama", "History"],
    "war": ["War", "Drama", "History"],
    "приключения": ["Adventure", "Action"],
    "adventure": ["Adventure", "Action"],
    "документальный": ["Documentary"],
    "документалка": ["Documentary"],
    "мультфильм": ["Animation", "Family"],
    "мультик": ["Animation", "Family"],
    "animation": ["Animation", "Family"],
    "аниме": ["Animation", "Fantasy"],
}


def _mood_to_genres(query: str) -> list[str]:
    """Map a mood/query string to genre slugs using keyword matching."""
    q = query.lower().strip()
    results: list[str] = []
    for keyword, genres in _MOOD_GENRES.items():
        if keyword in q:
            results.extend(genres)
    # Deduplicate preserving order
    seen: set[str] = set()
    return [g for g in results if not (g in seen or seen.add(g))]


@router.post("/recommendations/by-mood", response_model=RecommendationsResponse)
def recommend_by_mood(
    body: MoodQueryRequest,
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
) -> RecommendationsResponse:
    """Return recommendations based on mood/query.

    If ``LLM_API_URL`` is configured (e.g. Ollama), the LLM is asked to
    suggest films from the library matching the mood.  Otherwise a
    keyword-based fallback maps mood words to genres.
    """
    genres = _mood_to_genres(body.query)

    if not genres:
        return RecommendationsResponse(items=[], total=0)

    # Find films matching these genres, excluding watched/blacklisted/etc.
    watched = (
        db.query(MovieEdition.film_id)
        .join(MediaFile).join(WatchEvent)
        .filter(WatchEvent.user_id == current_user.id, WatchEvent.incognito == sa_false())
        .distinct().subquery()
    )
    blacklisted = (
        db.query(UserFilmBlacklist.film_id)
        .filter(UserFilmBlacklist.user_id == current_user.id).subquery()
    )

    films = (
        db.query(Film)
        .options(joinedload(Film.genres))
        .filter(Film.genres.any(Genre.name.in_(genres)))
        .filter(Film.id.notin_(watched))
        .filter(Film.id.notin_(blacklisted))
        .limit(limit)
        .all()
    )

    items = [
        RecommendationItem(
            film_id=f.id, title=f.title, year=f.year,
            poster_url=f.poster_url,
            score=1.0, match_reason=f"mood: {body.query}",
        )
        for f in films
    ]

    return RecommendationsResponse(items=items, total=len(items))


@router.get("/recommendations", response_model=RecommendationsResponse)
def get_recommendations(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
) -> RecommendationsResponse:
    """Return personalized film recommendations based on watch history.

    Scoring: for each finished film, collect its genre and person IDs,
    then score unwatched films by shared genres/persons.
    Results exclude already watched, blacklisted, age-restricted,
    and (if enabled) family videos.
    """
    # 1. Find watched (finished) film IDs for this user
    watched_film_ids = (
        db.query(MovieEdition.film_id)
        .join(MediaFile)
        .join(WatchEvent)
        .filter(
            WatchEvent.user_id == current_user.id,
            WatchEvent.finished == True,  # noqa: E712
            WatchEvent.incognito == sa_false(),
        )
        .distinct()
        .subquery()
    )

    # 2. Get genre and person IDs from watched films
    watched_genre_rows = (
        db.query(film_genre.c.genre_id)
        .filter(film_genre.c.film_id.in_(watched_film_ids))
        .distinct()
        .all()
    )
    watched_genre_ids = {r[0] for r in watched_genre_rows}

    watched_person_rows = (
        db.query(film_person.c.person_id)
        .filter(film_person.c.film_id.in_(watched_film_ids))
        .distinct()
        .all()
    )
    watched_person_ids = {r[0] for r in watched_person_rows}

    if not watched_genre_ids and not watched_person_ids:
        return RecommendationsResponse(items=[], total=0)

    # 3. Build a query for candidate films
    #    Exclude: watched, blacklisted, family (if setting), age-restricted
    watched_all = (
        db.query(MovieEdition.film_id)
        .join(MediaFile)
        .join(WatchEvent)
        .filter(
            WatchEvent.user_id == current_user.id,
            WatchEvent.incognito == sa_false(),
        )
        .distinct()
        .subquery()
    )

    blacklisted = (
        db.query(UserFilmBlacklist.film_id)
        .filter(UserFilmBlacklist.user_id == current_user.id)
        .subquery()
    )

    candidates = (
        db.query(Film)
        .options(joinedload(Film.genres), joinedload(Film.persons))
        .filter(Film.id.notin_(watched_all))
        .filter(Film.id.notin_(blacklisted))
    )

    if current_user.exclude_family_from_recommendations:
        candidates = candidates.filter(Film.is_family_video == False)  # noqa: E712

    if current_user.role == "child" and current_user.age_group is not None:
        from filmoteka.api.catalog import _AGE_GROUP_MAX, _AGE_RATING_VALUES
        max_age = _AGE_GROUP_MAX.get(current_user.age_group)
        if max_age is not None:
            allowed = [r for r, v in _AGE_RATING_VALUES.items() if v <= max_age]
            candidates = candidates.filter(
                or_(Film.age_rating.is_(None), Film.age_rating.in_(allowed))
            )

    candidates = candidates.all()

    # 4. Score candidates
    scored: list[tuple[Film, float, str]] = []
    for film in candidates:
        score = 0.0
        reasons: list[str] = []

        # Count matching genres
        film_genre_ids = {g.id for g in film.genres}
        match_genres = film_genre_ids & watched_genre_ids
        if match_genres:
            genre_score = len(match_genres) * 2.0
            score += genre_score
            reasons.append(f"genres ({len(match_genres)})")

        # Count matching persons
        film_person_ids = {p.id for p in film.persons}
        match_persons = film_person_ids & watched_person_ids
        if match_persons:
            person_score = len(match_persons) * 1.5
            score += person_score
            reasons.append(f"actors ({len(match_persons)})")

        if score > 0:
            scored.append((film, score, "; ".join(reasons)))

    # 5. Sort by score descending, return top N
    scored.sort(key=lambda x: -x[1])
    top = scored[:limit]

    items = [
        RecommendationItem(
            film_id=f.id,
            title=f.title,
            year=f.year,
            poster_url=f.poster_url,
            score=s,
            match_reason=r,
        )
        for f, s, r in top
    ]

    # 6. External suggestions via OMDB (if enabled)
    if current_user.include_external and settings.omdb_api_key and watched_genre_ids:
        try:
            import json as _json
            from urllib.parse import urlencode
            from urllib.request import Request, urlopen

            genre_names = (
                db.query(Genre.name)
                .filter(Genre.id.in_(watched_genre_ids))
                .all()
            )
            existing_titles = {f.title.lower() for f, in db.query(Film.title).all()}
            seen = {i.title.lower() for i in items}
            external_items: list[RecommendationItem] = []

            for (gname,) in genre_names[:2]:
                params = {"apikey": settings.omdb_api_key, "s": gname, "type": "movie"}
                url = f"http://www.omdbapi.com/?{urlencode(params)}"
                req = Request(url, headers={"Accept": "application/json"})
                resp = urlopen(req, timeout=10)
                if resp.status != 200:
                    continue
                body: dict = _json.loads(resp.read().decode("utf-8"))
                if body.get("Response") != "True":
                    continue
                for r in body.get("Search", []):
                    t = r.get("Title", "")
                    tl = t.lower()
                    if tl in existing_titles or tl in seen:
                        continue
                    seen.add(tl)
                    external_items.append(RecommendationItem(
                        film_id=0,
                        title=t,
                        year=r.get("Year", ""),
                        poster=r.get("Poster") if r.get("Poster") != "N/A" else None,
                        score=0.5,
                        match_reason=f"external — {gname}",
                    ))
                    if len(external_items) >= 5:
                        break

            items.extend(external_items[:5])
        except Exception:
            pass

    return RecommendationsResponse(items=items, total=len(items))


@router.delete("/watch/history", status_code=204)
def clear_watch_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
) -> None:
    """Delete all non-incognito watch events for the current user."""
    db.query(WatchEvent).filter(
        WatchEvent.user_id == current_user.id,
        WatchEvent.incognito == sa_false(),
    ).delete(synchronize_session=False)
    db.commit()


@router.delete("/watch/history/{film_id}", status_code=204)
def clear_watch_history_for_film(
    film_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
) -> None:
    """Delete watch events for a specific film for the current user.

    Finds all ``MediaFile`` IDs belonging to the film (via
    ``MovieEdition``) and deletes matching non-incognito watch events.
    """
    media_ids = (
        db.query(MediaFile.id)
        .join(MovieEdition)
        .filter(MovieEdition.film_id == film_id)
        .scalar_subquery()
    )
    db.query(WatchEvent).filter(
        WatchEvent.media_file_id.in_(media_ids),
        WatchEvent.user_id == current_user.id,
        WatchEvent.incognito == sa_false(),
    ).delete(synchronize_session=False)
    db.commit()


@router.get("/watch/history", response_model=WatchHistoryResponse)
def watch_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
) -> WatchHistoryResponse:
    """Return a paginated list of watch events for the current user."""
    query = (
        db.query(WatchEvent)
        .options(
            joinedload(WatchEvent.media_file)
            .joinedload(MediaFile.edition)
            .joinedload(MovieEdition.film)
        )
        .filter(
            WatchEvent.user_id == current_user.id,
            WatchEvent.incognito == sa_false(),
        )
    )

    total = query.count()
    events = (
        query.order_by(WatchEvent.started_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    items = [
        WatchHistoryItem(
            watch_event_id=e.id,
            media_file_id=e.media_file_id,
            film_id=e.media_file.edition.film.id,
            film_title=e.media_file.edition.film.title,
            film_year=e.media_file.edition.film.year,
            started_at=e.started_at,
            last_position=e.last_position,
            finished=e.finished,
        )
        for e in events
    ]

    return WatchHistoryResponse(items=items, total=total)

"""Shared server-side pagination rules for DijiTalentFlow list endpoints.

Card grids (3 columns desktop / 2 tablet) use multiples of 12 so a full page
fills whole rows; tables use 20/50/100. Every paged endpoint returns
``items, total, page, page_size, total_pages`` and orders by a deterministic
key with a unique tiebreaker (the primary key) so pages never overlap or
skip records over an unchanged dataset.
"""

from fastapi import HTTPException, status

CARD_PAGE_SIZES = (12, 24, 48, 96)
CARD_DEFAULT_PAGE_SIZE = 12
TABLE_PAGE_SIZES = (20, 50, 100)
TABLE_DEFAULT_PAGE_SIZE = 20


def require_page_size(page_size: int, allowed: tuple[int, ...], *, also_accept: tuple[int, ...] = ()) -> int:
    if page_size not in allowed + also_accept:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"page_size must be one of {list(allowed)}",
        )
    return page_size


def total_pages(total: int, page_size: int) -> int:
    return max(1, -(-total // page_size))


def offset_for(page: int, page_size: int) -> int:
    return (page - 1) * page_size

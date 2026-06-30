"""Compatibility shim for the unmaintained ``holidays_ext`` package.

Mirrors the public API of ``holidays_ext.get_holidays`` (``get_holiday``,
``get_holiday_df``, ``get_available_holiday_lookup_countries``,
``get_available_holidays_in_countries``,
``get_available_holidays_across_countries``) but delegates to the upstream
``holidays`` package, which now covers all countries that ``holidays_ext``
previously added.
"""

from datetime import datetime
from typing import List, Optional

import holidays
import pandas as pd


def _country_holidays(country: str, years):
    return holidays.country_holidays(country, years=list(years))


def get_holiday(country_list: List[str], years: List[int]) -> dict:
    """Look up holidays for ``country_list`` over ``years``.

    Returns a dict mapping country code/name to a
    ``holidays.HolidayBase``-like mapping of date → name.
    """
    result = {}
    for country in country_list:
        try:
            result[country] = _country_holidays(country, years)
        except (KeyError, NotImplementedError) as e:
            raise AttributeError(
                f"Holidays in {country} are not currently supported!"
            ) from e
    return result


def get_holiday_df(country_list: List[str], years: List[int]) -> pd.DataFrame:
    """Return a DataFrame with one row per (country, holiday-date)."""
    country_holidays = get_holiday(country_list=country_list, years=years)
    dfs = []
    for country, country_holidays_map in country_holidays.items():
        if len(country_holidays_map) == 0:
            continue
        temp_df = pd.DataFrame(
            {
                "ts": pd.to_datetime(list(country_holidays_map.keys())),
                "holiday": list(country_holidays_map.values()),
            }
        )
        temp_df["country"] = country
        temp_df["country_holiday"] = temp_df["country"] + "_" + temp_df["holiday"]
        dfs.append(temp_df)
    if not dfs:
        return pd.DataFrame(columns=["ts", "country", "holiday", "country_holiday"])
    return pd.concat(dfs, axis=0).reset_index(drop=True)[
        ["ts", "country", "holiday", "country_holiday"]
    ]


def _all_supported_countries() -> List[str]:
    countries = set()
    registry = getattr(holidays, "registry", None)
    if registry is not None:
        entity = getattr(registry, "EntityLoader", None)
        if entity is not None and hasattr(entity, "_entities"):
            countries.update(entity._entities().keys())
    try:
        list_supported = holidays.list_supported_countries()
    except AttributeError:
        list_supported = {}
    for full_name, codes in list_supported.items():
        countries.add(full_name)
        if isinstance(codes, (list, tuple)):
            countries.update(codes)
        elif codes:
            countries.add(codes)
    # Also include long-form class names like ``UnitedStates`` /
    # ``UnitedKingdom`` / ``India`` that ``holidays.country_holidays`` still
    # accepts via class lookup even though they're absent from the
    # ``list_supported_countries`` registry.
    try:
        import holidays.countries as _hc
        import inspect as _inspect
        for name, cls in _inspect.getmembers(_hc, _inspect.isclass):
            if hasattr(cls, "country") and not name.startswith("_"):
                countries.add(name)
    except (ImportError, AttributeError):
        pass
    return sorted(c for c in countries if c)


def get_available_holiday_lookup_countries(
    countries: Optional[List[str]] = None,
) -> List[str]:
    """Return supported country names/codes, optionally filtered."""
    available = set(_all_supported_countries())
    if countries is None:
        return sorted(available)
    return sorted(c for c in set(countries) if c in available)


def _default_year_range(year_start, year_end):
    if year_start is None:
        year_start = 1985
    if year_end is None:
        current_year = datetime.now().year
        year_end = current_year if current_year >= year_start else year_start
    return year_start, year_end


def get_available_holidays_in_countries(
    countries: List[str],
    year_start: Optional[int] = None,
    year_end: Optional[int] = None,
) -> dict:
    """Map each country to the sorted list of holiday names in the year range."""
    year_start, year_end = _default_year_range(year_start, year_end)
    country_holidays = get_holiday(
        country_list=countries, years=list(range(year_start, year_end + 1))
    )
    return {
        country: sorted({name for name in holiday.values()})
        for country, holiday in country_holidays.items()
    }


def get_available_holidays_across_countries(
    countries: List[str],
    year_start: Optional[int] = None,
    year_end: Optional[int] = None,
) -> List[str]:
    """Union of holiday names across ``countries`` in the year range."""
    country_holidays = get_available_holidays_in_countries(
        countries=countries, year_start=year_start, year_end=year_end
    )
    return sorted({h for h_list in country_holidays.values() for h in h_list})

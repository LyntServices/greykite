# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Fork context

This is **LyntServices' fork of LinkedIn's `greykite`** (`pyproject.toml` declares it as `Fork of greykite 1.0.0`). The fork's purpose is to make the library installable under Python 3.11–3.13 with updated dependencies (`cvxpy>=1.6`, `scipy`, `pandas 2.2+`, `numpy 2.x`, `scikit-learn>=1.5.2`, `statsmodels>=0.14.3`, `pmdarima>=2.1`, etc.). Two parallel dependency declarations live in the repo and they intentionally disagree:

- `pyproject.toml` (uv / PEP 621) + `uv.lock` — **authoritative for this fork**. `requires-python = ">=3.11,<3.14"`, semver ranges (no exact pins), dev tools in the `dev` dependency group. Build backend is `uv_build`. The `[tool.uv]` table contains a couple of `constraint-dependencies` (e.g., `scs>=3.2.7`, `rpds-py>=0.19.1`) to force transitive deps onto versions that ship cp313 wheels.
- `setup.py` + `requirements-dev.txt` — inherited from upstream, targets Python 3.10 with older pins (pandas `<2.0.0`, scipy `<1.11.0`, etc.). Do not treat these as the source of truth; they remain for compatibility with upstream tooling but the install path is uv.

When updating dependencies or Python version constraints, change `pyproject.toml` and re-lock with `uv lock`. The `setup.py` pins are stale by design.

The project was migrated from Poetry to uv (see commit history). `.python-version` pins 3.13 by default; uv will fetch the matching interpreter automatically. Python 3.11 is still supported and tested.

The `holidays_ext` PyPI package (last released 2022, unmaintained) is incompatible with the modern `holidays` package, so this fork ships a small in-repo shim at `greykite/common/features/_holidays_lookup.py` that exposes the same `get_holiday`, `get_holiday_df`, `get_available_holiday_lookup_countries`, `get_available_holidays_in_countries`, `get_available_holidays_across_countries` functions backed directly by upstream `holidays`. Several upstream holiday names have changed since this fork was originally built (e.g. `Chinese New Year` → `Chinese New Year (Spring Festival)`, `Thanksgiving` → `Thanksgiving Day`, `Easter Monday [England, Wales, Northern Ireland]` → `Easter Monday`, suffix `(Observed)` → `(observed)`); the silverkite `HOLIDAY_LOOKUP_COUNTRIES_AUTO` / `HOLIDAYS_TO_MODEL_SEPARATELY_AUTO` / `HOLIDAY_IMPACT_DICT` / `HOLIDAYS_TO_INTERACT` constants and the `HolidayInferrer._get_holiday_df` suffix matcher have been updated accordingly.

The ECOS solver is no longer shipped with `cvxpy>=1.6`. Greykite now uses `cvxpy.CLARABEL` instead (in `algo/common/l1_quantile_regression.py` and `algo/reconcile/convex/reconcile_forecasts.py`).

## Common commands

Install / develop (uv is the supported flow in this fork):

```
uv sync --all-groups   # creates .venv with runtime + dev deps from uv.lock
uv lock                # regenerate uv.lock after editing pyproject.toml
```

Test, lint, docs — the `Makefile` targets still work but expect the tools to be on `PATH`. Either activate the venv (`source .venv/bin/activate`) or prefix commands with `uv run`:

```
uv run make test       # pytest greykite/tests
uv run make flake8     # style check, ignores W503,W504,F541,E226,E126,E402,E123,E121,E741
uv run make coverage   # coverage run + html report
uv run make docs       # sphinx build under docs/
```

Single test / subset:

```
uv run pytest greykite/tests/framework/templates/test_forecaster.py
uv run pytest greykite/tests/framework/templates/test_forecaster.py::test_run_forecast_config -q
uv run pytest greykite/tests -k silverkite
```

`tox.ini` still lists `py37`/`py38` envs from upstream and is not used for this fork — use `uv run pytest` directly.

`flake8` config note: `setup.cfg` defines a `max-line-length = 160` and one ignore list, but `make flake8` and `tox` invoke flake8 with a longer ignore list on the CLI. The CLI-passed list is what gates contributions; `setup.cfg`'s shorter list applies if you run `flake8` bare.

## Architecture

Greykite is a layered forecasting + anomaly-detection library. The layers below are *the* mental model for navigating the codebase — most user-facing flows traverse them top-down.

1. **`greykite.framework.templates`** — user-facing entry point.
   - `Forecaster.run_forecast_config(df, config: ForecastConfig)` (`framework/templates/forecaster.py`) is the canonical entry point used in the README example.
   - `ModelTemplateEnum` (`framework/templates/model_templates.py`) names preset configurations (`SILVERKITE`, `AUTO`, `SILVERKITE_MONTHLY`, `SILVERKITE_WOW`, `PROPHET`, `AUTO_ARIMA`, multistage variants).
   - Each template (`simple_silverkite_template.py`, `silverkite_template.py`, `prophet_template.py`, `auto_arima_template.py`, `lag_based_template.py`, `multistage_forecast_template.py`) implements `TemplateInterface` and turns a `ForecastConfig` into a configured sklearn `Pipeline`.
   - `autogen/forecast_config.py` holds the dataclasses (`ForecastConfig`, `MetadataParam`, `ModelComponentsParam`, `EvaluationPeriodParam`, etc.). These are auto-generated dataclasses — edits should preserve the structure that the autogen consumers expect.

2. **`greykite.framework.pipeline`** — `forecast_pipeline()` wires together preprocessing, CV grid search, backtest, and final fit. Returns a `ForecastResult` containing `forecast`, `backtest`, `grid_search`, `model`, `timeseries`.

3. **`greykite.sklearn.estimator`** — scikit-learn-compatible estimators that wrap the underlying algorithms:
   - `SimpleSilverkiteEstimator`, `SilverkiteEstimator`, `BaseSilverkiteEstimator` — flagship algorithm.
   - `ProphetEstimator`, `AutoArimaEstimator`, `LagBasedEstimator`, `MultistageForecastEstimator`, `OneByOneEstimator`.
   - These are the bridge between the template/pipeline layer and the algorithmic core.

4. **`greykite.algo`** — algorithmic core, framework-agnostic.
   - `algo/forecast/silverkite/` — Silverkite implementation (`SilverkiteForecast`, `SimpleSilverkiteForecast`).
   - `algo/changepoint/` — adaptive-lasso changepoint detection + level-shift detection (`adalasso/`, `shift_detection/`).
   - `algo/reconcile/` — additive forecast reconciliation (`ReconcileAdditiveForecasts`).
   - `algo/uncertainty/` — conditional quantile/uncertainty methods used for prediction intervals.

5. **`greykite.common`** — shared utilities used by all upper layers: `data_loader.py` (sample datasets), `evaluation.py` (metrics), `features/` (timeseries features, outliers, changepoint feature builders), `viz/` (plotly-based plotting), `constants.py` / `enums.py` (column names, frequency aliases — these are referenced widely, don't rename casually).

6. **`greykite.detection`** — anomaly-detection extension added in 1.0.0. `detection/detector/` (notably `GreykiteDetector`) builds on top of Silverkite forecasts and tunes confidence intervals against alert-rate / labels. `detection/common/pickler.py` (`GreykitePickler`) is the supported way to persist Greykite models in a single file.

### Tests

`greykite/tests/` mirrors the package layout 1:1 (`tests/framework/templates/`, `tests/algo/forecast/silverkite/`, etc.). When adding tests, place them in the matching directory; `make test` discovers everything under `greykite/tests`.

### Style

- Code style is `flake8` with the ignore list from `make flake8` / `tox.ini`. Docstrings follow `numpydoc`.
- Docs are built via Sphinx + `sphinx-gallery`; gallery examples live under `docs/`.

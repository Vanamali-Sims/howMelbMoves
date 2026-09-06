# Notebooks

Notebooks are for exploration only.

Do not treat a notebook as a pipeline step. If a cell is worth reusing — a join,
a quality check, a feature, a plot that will be regenerated — move that code
into `src/melbourne_footfall/` or a dbt model and call it from the notebook.

Notebooks must not write into `data/raw/`. Raw extracts are immutable.

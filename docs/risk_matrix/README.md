# Risk Matrix

This directory keeps the repository copy of the MamaAir risk-factor matrix.

The matrix is stored in two forms:

- `risk_factor_matrix.yaml` is the structured source for review and future automated checks.
- `risk_factor_matrix.md` is the human-readable table for product and engineering review.

Supporting notes:

- `source_notes.md` records source-document naming and product mapping decisions.
- `out_of_scope.md` records source-document items that are intentionally not implemented yet.

The Django migration remains self-contained. The YAML file is documentation and a review artifact; migrations should not read it at runtime.

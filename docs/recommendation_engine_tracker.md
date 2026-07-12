# Recommendation engine implementation tracker

The current implementation status of MamaAir recommendations is maintained in the shared Google Sheet:

[MamaAir Recommendation Engine — Implementation Tracker](https://docs.google.com/spreadsheets/d/1Ue8JR9QXxyPe3hMOwIMVTsT_qKZb7HDmcs1reqYE8C0/edit)

The tracker covers:

- implemented, partially implemented, not implemented, and blocked recommendation areas;
- the corresponding engine `rule_id` where one exists;
- existing behavior in the current codebase;
- missing data, product decisions, or engine capabilities;
- agreed project decisions.

The Google Sheet is the single source of truth for implementation coverage. Do not maintain a duplicate recommendation matrix in this repository.

When a pull request changes recommendation logic, its author should update the corresponding tracker rows as part of the same work.

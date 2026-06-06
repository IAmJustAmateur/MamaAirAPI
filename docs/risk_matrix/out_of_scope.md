# Risk Matrix Scope Notes

Source: `10 Risk Matrix model (2).odt`.

This note records the parts of the new risk matrix that are intentionally not implemented in the current migration pass.

## Implemented In This Pass

The current pass updates risk-factor seed data that can be expressed with the existing risk engine and existing profile/lifestyle fields:

- Profile factors via `UserRiskFactor`:
  - BMI
  - Age
  - Race
- Lifestyle factors via `LifestyleRiskFactor`:
  - Sleep duration
  - Exercise duration
  - Work type
  - Household fuel

Risk names remain aligned with the existing database catalog:

- `Hyperemesis`, not `Hyperemesis Gravidarum`
- `Cardiovascular Complications`, not `Cardio Vascular Complications`
- `Low Birth Weight` remains unchanged

Work-type mapping used for this pass:

- Sedentary -> `Desk`
- Heavy manual / physical / mechanical labor -> `Physical`
- Shift work / night shifts -> existing `Night Shift`

Household fuel mapping used for this pass:

- Wood/Coal -> `cooking_method == "wood"` or `cooking_method == "charcoal"`
- No separate `coal` choice is added.

## Deferred Items

### Work Hours

The matrix contains `Work Hours >40 hrs/week`, but the current `UserLifeStyle` model does not have a `work_hours_per_week` field.

Deferred because adding this correctly requires:

- model field
- serializer/API contract update
- mobile/UI data collection decision
- migration and tests

For now, no work-hours risk factor is seeded.

### Temperature

The matrix contains temperature triggers such as:

- local percentile thresholds
- multiple-day heat exposure windows
- pregnancy-week windows, for example weeks 1-20, 28-36, 34-40, 39-40

Deferred because current risk inputs do not expose pregnancy-window temperature aggregates to the risk engine.

Implementing this correctly needs a separate environmental risk input layer that can compute:

- rolling temperature windows
- local percentile thresholds
- pregnancy-week-aware exposure windows
- per-user local calendar dates

### Solar UV

The matrix contains UV triggers such as:

- cumulative ambient UV
- daily UV thresholds
- pregnancy-week windows
- multi-day exposure windows

Deferred for the same reason as temperature: current risk inputs do not expose UV aggregates over pregnancy windows.

Implementing this correctly needs:

- UV aggregation from exposure logs
- cumulative and rolling-window features
- pregnancy-week-aware windows
- clear units and threshold semantics

### Gestational Window Constraints For Lifestyle/Profile Factors

Some lifestyle/profile rows in the matrix include pregnancy windows, for example sleep during weeks 1-26 or 26-39.

Deferred because the current `UserRiskFactor` and `LifestyleRiskFactor` models express simple conditions over the current profile/lifestyle object. They do not store or evaluate gestational windows.

The current pass applies the supported factor whenever the current profile/lifestyle condition matches, without gestational-window filtering.

### Exact Shift-Work Semantics

The matrix distinguishes variants such as shift work, night shifts, sedentary work, and heavy labor.

The current app only has a coarse `work_type` field. This pass maps those variants to existing choices instead of expanding the model:

- `Night Shift`
- `Desk`
- `Physical`

A more precise version would likely need either new choices or additional work schedule fields.

## Recommendation

Treat temperature, UV, work-hours, and gestational-window logic as a separate environmental/lifestyle risk-engine upgrade. They require new inputs and evaluation logic, not only data migrations.

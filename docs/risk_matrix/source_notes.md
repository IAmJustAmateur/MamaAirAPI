# Risk Matrix Source Notes

Source: `10 Risk Matrix model (2).odt`.

This document records the product and implementation decisions applied while translating the source matrix into the current Django seed migration.

## Naming Decisions

Existing risk names remain unchanged in the database:

- `Hyperemesis`, not `Hyperemesis Gravidarum`
- `Cardiovascular Complications`, not `Cardio Vascular Complications`
- `Low Birth Weight` remains unchanged

## App Field Mappings

Profile factors are implemented through `UserRiskFactor` using existing `User` fields:

- BMI -> `bmi`
- Maternal age -> `full_year`
- Race -> `race`

Lifestyle factors are implemented through `LifestyleRiskFactor` using existing `UserLifeStyle` fields:

- Sleep duration -> `average_sleep_hours`
- Exercise duration -> `activity_duration_minutes`
- Diet type -> `diet_type`
- Work type -> `work_type`
- Household fuel -> `cooking_method`

## Product Mappings

The source matrix has more granular lifestyle labels than the current app. This pass maps them to existing app choices:

- Sedentary work -> `work_type == "Desk"`
- Heavy manual / physical / mechanical labor -> `work_type == "Physical"`
- Shift work / night shifts -> `work_type == "Night Shift"`
- Wood/Coal household fuel -> `cooking_method == "wood"` or `cooking_method == "charcoal"`

No separate `coal` cooking-method choice is added. `charcoal` is treated as the current app equivalent of coal.

## Migration Policy

The migration is intentionally self-contained. It repeats the risk-factor data instead of reading `docs/risk_matrix/risk_factor_matrix.yaml` at migration runtime.

Future updates can use the YAML file as a review and test fixture, but production migrations should remain immutable snapshots.

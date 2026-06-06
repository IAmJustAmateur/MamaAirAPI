# Risk Factor Matrix

Source document: `10 Risk Matrix model (2).odt`

Implementation migration: `api/migrations/0043_seed_risk_factor_matrix.py`

This table records the risk-factor rows implemented with the current profile and lifestyle models. Status values:

- `implemented`: direct app-field representation.
- `mapped`: implemented through an explicit product mapping to an existing app choice.
- `deferred`: present in the source matrix but not implemented in this migration pass.

## Risk Priorities

| Risk | Priority |
| --- | ---: |
| Preeclampsia | 1 |
| Preterm birth | 2 |
| GDM | 3 |
| Low Birth Weight | 4 |
| Placental abruption | 5 |
| Anemia | 6 |
| PROM | 7 |
| Hyperemesis | 8 |
| Cardiovascular Complications | 9 |
| Fetal Hypoxia | 10 |

## Implemented Factors

| Risk | Source factor | Model | App field | Condition | Multiplier | Status | Notes |
| --- | --- | --- | --- | --- | ---: | --- | --- |
| Preeclampsia | BMI | UserRiskFactor | `bmi` | `bmi>=25` | 2.8 | implemented |  |
| Preeclampsia | Maternal age | UserRiskFactor | `full_year` | `full_year>=35` | 1.8 | implemented |  |
| Preeclampsia | Race | UserRiskFactor | `race` | `'race'=='african'` | 1.6 | implemented |  |
| Preeclampsia | Sleep duration | LifestyleRiskFactor | `average_sleep_hours` | `average_sleep_hours<=6` | 1.4 | implemented |  |
| Preeclampsia | Exercise duration | LifestyleRiskFactor | `activity_duration_minutes` | `activity_duration_minutes>=420` | 0.76 | implemented |  |
| Preeclampsia | Shift work / night shifts | LifestyleRiskFactor | `work_type` | `'work_type'=='Night Shift'` | 1.75 | mapped | Uses existing `Night Shift`. |
| Preeclampsia | Wood/Coal household fuel | LifestyleRiskFactor | `cooking_method` | `'cooking_method'=='wood' or 'cooking_method'=='charcoal'` | 2.2 | mapped | `charcoal` is treated as coal equivalent. |
| Preterm birth | Maternal age | UserRiskFactor | `full_year` | `full_year<=16` | 1.5 | implemented |  |
| Preterm birth | Maternal age | UserRiskFactor | `full_year` | `full_year>35 and full_year<=40` | 1.2 | implemented |  |
| Preterm birth | Maternal age | UserRiskFactor | `full_year` | `full_year>40` | 1.4 | implemented |  |
| Preterm birth | BMI | UserRiskFactor | `bmi` | `bmi<18.5` | 1.07 | implemented |  |
| Preterm birth | Sleep duration | LifestyleRiskFactor | `average_sleep_hours` | `average_sleep_hours<6` | 1.23 | implemented |  |
| Preterm birth | Shift work / night shifts | LifestyleRiskFactor | `work_type` | `'work_type'=='Night Shift'` | 1.21 | mapped | Uses existing `Night Shift`. |
| Preterm birth | Wood/Coal household fuel | LifestyleRiskFactor | `cooking_method` | `'cooking_method'=='wood' or 'cooking_method'=='charcoal'` | 1.3 | mapped | `charcoal` is treated as coal equivalent. |
| GDM | BMI | UserRiskFactor | `bmi` | `bmi>=30` | 4.0 | implemented |  |
| GDM | Race | UserRiskFactor | `race` | `'race'=='african'` | 1.11 | implemented |  |
| GDM | Sleep duration | LifestyleRiskFactor | `average_sleep_hours` | `average_sleep_hours<7` | 1.75 | implemented |  |
| GDM | Shift work / night shifts | LifestyleRiskFactor | `work_type` | `'work_type'=='Night Shift'` | 1.75 | mapped | Uses existing `Night Shift`. |
| GDM | Exercise duration | LifestyleRiskFactor | `activity_duration_minutes` | `activity_duration_minutes>=150` | 0.7 | implemented | Protective multiplier. |
| GDM | Diet type | LifestyleRiskFactor | `diet_type` | `'diet_type'=='vegetarian'` | 1.09 | implemented |  |
| Low Birth Weight | Maternal age | UserRiskFactor | `full_year` | `full_year<20` | 1.56 | implemented | Existing risk name retained. |
| Low Birth Weight | BMI | UserRiskFactor | `bmi` | `bmi<19` | 1.7 | implemented | Existing risk name retained. |
| Low Birth Weight | Race | UserRiskFactor | `race` | `'race'=='african'` | 2.0 | implemented | Existing risk name retained. |
| Low Birth Weight | Shift work / night shifts | LifestyleRiskFactor | `work_type` | `'work_type'=='Night Shift'` | 1.18 | mapped | Uses existing `Night Shift`. |
| Low Birth Weight | Wood/Coal household fuel | LifestyleRiskFactor | `cooking_method` | `'cooking_method'=='wood' or 'cooking_method'=='charcoal'` | 1.74 | mapped | `charcoal` is treated as coal equivalent. |
| Placental abruption | Maternal age | UserRiskFactor | `full_year` | `full_year>=35` | 1.62 | implemented |  |
| Placental abruption | BMI | UserRiskFactor | `bmi` | `bmi<18.5` | 1.38 | implemented |  |
| Placental abruption | Race | UserRiskFactor | `race` | `'race'=='african'` | 1.32 | implemented |  |
| Placental abruption | Sleep duration | LifestyleRiskFactor | `average_sleep_hours` | `average_sleep_hours>9 or average_sleep_hours<6` | 1.3 | implemented |  |
| Placental abruption | Sedentary work | LifestyleRiskFactor | `work_type` | `'work_type'=='Desk'` | 17.3 | mapped | Sedentary is mapped to `Desk`. |
| Anemia | BMI | UserRiskFactor | `bmi` | `bmi<18.5` | 1.57 | implemented |  |
| Anemia | Maternal age | UserRiskFactor | `full_year` | `full_year<19 or full_year>=40` | 1.45 | implemented |  |
| Anemia | Race | UserRiskFactor | `race` | `'race'=='african'` | 2.1 | implemented |  |
| Anemia | Sleep duration | LifestyleRiskFactor | `average_sleep_hours` | `average_sleep_hours<=6` | 1.38 | implemented |  |
| Anemia | Exercise duration | LifestyleRiskFactor | `activity_duration_minutes` | `activity_duration_minutes<420` | 1.3 | implemented |  |
| Anemia | Heavy manual / physical / mechanical labor | LifestyleRiskFactor | `work_type` | `'work_type'=='Physical'` | 1.55 | mapped | Labor variants are mapped to `Physical`. |
| Anemia | Wood/Coal household fuel | LifestyleRiskFactor | `cooking_method` | `'cooking_method'=='wood' or 'cooking_method'=='charcoal'` | 1.68 | mapped | `charcoal` is treated as coal equivalent. |
| PROM | BMI | UserRiskFactor | `bmi` | `bmi<18.5` | 1.62 | implemented |  |
| PROM | Maternal age | UserRiskFactor | `full_year` | `full_year>=35` | 1.32 | implemented |  |
| PROM | Race | UserRiskFactor | `race` | `'race'=='african'` | 1.85 | implemented |  |
| PROM | Sleep duration | LifestyleRiskFactor | `average_sleep_hours` | `average_sleep_hours<=6` | 1.35 | implemented |  |
| PROM | Exercise duration | LifestyleRiskFactor | `activity_duration_minutes` | `activity_duration_minutes<420` | 1.3 | implemented |  |
| PROM | Heavy manual / physical / mechanical labor | LifestyleRiskFactor | `work_type` | `'work_type'=='Physical'` | 1.52 | mapped | Labor variants are mapped to `Physical`. |
| PROM | Wood/Coal household fuel | LifestyleRiskFactor | `cooking_method` | `'cooking_method'=='wood' or 'cooking_method'=='charcoal'` | 1.45 | mapped | `charcoal` is treated as coal equivalent. |
| Hyperemesis | BMI | UserRiskFactor | `bmi` | `bmi>=25` | 1.32 | implemented | Existing risk name retained. |
| Hyperemesis | Maternal age | UserRiskFactor | `full_year` | `full_year<19` | 1.41 | implemented | Existing risk name retained. |
| Hyperemesis | Race | UserRiskFactor | `race` | `'race'=='african'` | 1.53 | implemented | Existing risk name retained. |
| Hyperemesis | Sleep duration | LifestyleRiskFactor | `average_sleep_hours` | `average_sleep_hours<=6` | 1.45 | implemented |  |
| Hyperemesis | Exercise duration | LifestyleRiskFactor | `activity_duration_minutes` | `activity_duration_minutes<420` | 1.18 | implemented |  |
| Hyperemesis | Shift work / night shifts | LifestyleRiskFactor | `work_type` | `'work_type'=='Night Shift'` | 1.36 | mapped | Uses existing `Night Shift`. |
| Hyperemesis | Wood/Coal household fuel | LifestyleRiskFactor | `cooking_method` | `'cooking_method'=='wood' or 'cooking_method'=='charcoal'` | 1.38 | mapped | `charcoal` is treated as coal equivalent. |
| Cardiovascular Complications | BMI | UserRiskFactor | `bmi` | `bmi>=30` | 1.95 | implemented | Existing risk name retained. |
| Cardiovascular Complications | Maternal age | UserRiskFactor | `full_year` | `full_year>35` | 1.35 | implemented | Existing risk name retained. |
| Cardiovascular Complications | Race | UserRiskFactor | `race` | `'race'=='african'` | 1.54 | implemented | Existing risk name retained. |
| Cardiovascular Complications | Sleep duration | LifestyleRiskFactor | `average_sleep_hours` | `average_sleep_hours<=6` | 1.42 | implemented |  |
| Cardiovascular Complications | Exercise duration | LifestyleRiskFactor | `activity_duration_minutes` | `activity_duration_minutes<420` | 1.35 | implemented |  |
| Cardiovascular Complications | Shift work / night shifts | LifestyleRiskFactor | `work_type` | `'work_type'=='Night Shift'` | 1.48 | mapped | Uses existing `Night Shift`. |
| Cardiovascular Complications | Wood/Coal household fuel | LifestyleRiskFactor | `cooking_method` | `'cooking_method'=='wood' or 'cooking_method'=='charcoal'` | 1.65 | mapped | `charcoal` is treated as coal equivalent. |
| Fetal Hypoxia | BMI | UserRiskFactor | `bmi` | `bmi>=25` | 1.65 | implemented |  |
| Fetal Hypoxia | Maternal age | UserRiskFactor | `full_year` | `full_year>35` | 1.4 | implemented |  |
| Fetal Hypoxia | Race | UserRiskFactor | `race` | `'race'=='african'` | 1.5 | implemented |  |
| Fetal Hypoxia | Sleep duration | LifestyleRiskFactor | `average_sleep_hours` | `average_sleep_hours<=6` | 1.8 | implemented |  |
| Fetal Hypoxia | Exercise duration | LifestyleRiskFactor | `activity_duration_minutes` | `activity_duration_minutes<420` | 1.25 | implemented |  |
| Fetal Hypoxia | Heavy manual / physical / mechanical labor | LifestyleRiskFactor | `work_type` | `'work_type'=='Physical'` | 1.35 | mapped | Labor variants are mapped to `Physical`. |
| Fetal Hypoxia | Wood/Coal household fuel | LifestyleRiskFactor | `cooking_method` | `'cooking_method'=='wood' or 'cooking_method'=='charcoal'` | 1.65 | mapped | `charcoal` is treated as coal equivalent. |

## Deferred Source Items

| Source item | Status | Reason |
| --- | --- | --- |
| Work Hours >40 hrs/week | deferred | No `work_hours_per_week` field exists yet. |
| Temperature | deferred | Requires rolling exposure windows, local percentiles, and pregnancy-week-aware environmental inputs. |
| Solar UV | deferred | Requires UV aggregation, cumulative or rolling windows, and pregnancy-week-aware environmental inputs. |
| Gestational window constraints for profile/lifestyle factors | deferred | Current factor models do not store or evaluate gestational windows. |

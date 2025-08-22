def calculate_exposure(aq_risks):
    integrated_aq_risk = 1
    for risk in aq_risks:
        integrated_aq_risk *= aq_risks[risk]
    return integrated_aq_risk

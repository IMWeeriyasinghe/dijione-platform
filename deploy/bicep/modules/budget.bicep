// A monthly cost budget + alert for one DijiOne resource group (Amendment 6 /
// Amendment 8 cost control). Alerts at 80% actual and 100% forecast spend.
// Deployed separately (not from foundation.bicep) so the budget lifecycle is
// independent of the infrastructure.

targetScope = 'resourceGroup'

@description('Budget name, e.g. dijione-dev-monthly.')
param name string

@description('Monthly amount in the billing currency.')
param amount int

@description('First day of a month, YYYY-MM-DD (UTC).')
param startDate string

@description('End of the budget window, YYYY-MM-DD (UTC).')
param endDate string

@description('Email(s) to notify.')
param contactEmails array

resource budget 'Microsoft.Consumption/budgets@2023-11-01' = {
  name: name
  properties: {
    category: 'Cost'
    amount: amount
    timeGrain: 'Monthly'
    timePeriod: {
      startDate: startDate
      endDate: endDate
    }
    notifications: {
      actual_GreaterThan_80_Percent: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 80
        thresholdType: 'Actual'
        contactEmails: contactEmails
      }
      forecasted_GreaterThan_100_Percent: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 100
        thresholdType: 'Forecasted'
        contactEmails: contactEmails
      }
    }
  }
}

output id string = budget.id

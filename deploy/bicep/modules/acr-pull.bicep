// Grants AcrPull on a container registry to one Container App / Job identity.
//
// This is its own module because the registry can live in a DIFFERENT resource
// group from the workloads (Amendment 4: crdijionenonprod in rg-dijione-shared,
// shared by DEV + UAT). A role assignment must be authored at the target
// resource's scope, so main.bicep invokes this with
// `scope: resourceGroup(imageRegistryResourceGroup)`.
//
// The assignment name is start-time deterministic (guid of stable strings) so
// the deployment can plan it without waiting on the app module's output.

@description('Registry name, e.g. crdijionenonprod. Must exist in this module\'s resource group.')
param acrName string

@description('Stable identifier for the grantee (the app/job name) — only used to make the assignment name unique.')
param granteeName string

@description('The Container App / Job system-assigned identity principalId.')
param principalId string

var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' existing = {
  name: acrName
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, granteeName, acrPullRoleId)
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

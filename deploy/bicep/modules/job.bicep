// One DijiOne Container Apps Job. Two shapes:
//   - Schedule: the source-sync jobs (cron -> authenticated internal POST)
//   - Manual:   the per-service `migrate` job (alembic upgrade head)
// Migration-execution ownership stays with the schema owner: a `migrate`
// job uses ITS OWN service image, not one shared platform-api image.

@description('Job name, e.g. recruitment-sync-job or migrate-talent-api.')
param name string

@description('Image to run — the OWNING service\'s image for a migrate job.')
param image string

param managedEnvironmentId string
param acrLoginServer string

@description('Resource id of the shared user-assigned identity (id-dijione-<env>) used for ACR pull + Key Vault secret resolution.')
param userAssignedIdentityId string

param workloadProfileName string = 'Consumption'
param location string = resourceGroup().location
param tags object = {}

@description('Schedule | Manual')
@allowed([ 'Schedule', 'Manual' ])
param triggerType string = 'Manual'

@description('Cron (UTC), only used when triggerType == Schedule.')
param cronExpression string = '0 0 * * *'

param replicaTimeout int = 900
param cpu string = '0.25'
param memory string = '0.5Gi'

@description('Container command, e.g. [ "/bin/sh" ].')
param command array = []

@description('Container args.')
param args array = []

@description('Plain env vars [{ name, value }].')
param envVars array = []

@description('Key Vault-backed secrets [{ name, keyVaultUrl, envName }].')
param secretRefs array = []

var acaSecrets = [
  for s in secretRefs: {
    name: s.name
    keyVaultUrl: s.keyVaultUrl
    identity: userAssignedIdentityId
  }
]
var secretEnv = [
  for s in secretRefs: {
    name: s.envName
    secretRef: s.name
  }
]

var scheduleConfig = triggerType == 'Schedule'
  ? {
      scheduleTriggerConfig: {
        cronExpression: cronExpression
        parallelism: 1
        replicaCompletionCount: 1
      }
    }
  : {
      manualTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
      }
    }

resource job 'Microsoft.App/jobs@2024-03-01' = {
  name: name
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned, UserAssigned'
    userAssignedIdentities: {
      '${userAssignedIdentityId}': {}
    }
  }
  properties: {
    environmentId: managedEnvironmentId
    workloadProfileName: workloadProfileName
    configuration: union(
      {
        triggerType: triggerType
        replicaTimeout: replicaTimeout
        replicaRetryLimit: 1
        registries: [
          {
            server: acrLoginServer
            identity: userAssignedIdentityId
          }
        ]
        secrets: acaSecrets
      },
      scheduleConfig
    )
    template: {
      containers: [
        {
          name: name
          image: image
          command: empty(command) ? null : command
          args: empty(args) ? null : args
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: concat(envVars, secretEnv)
        }
      ]
    }
  }
}

// ACR pull + Key Vault secret access come from the shared UAMI
// (userAssignedIdentityId), granted before this module runs. The
// system-assigned identity is retained for future per-service grants but
// carries no role assignment here.

output systemPrincipalId string = job.identity.principalId
output name string = job.name

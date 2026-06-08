// Azure infrastructure for the Economic Indicators ETL pipeline.
//
// Deploys, at resource-group scope, everything the pipeline needs to run as a
// managed, scheduled cloud job — no servers to babysit:
//
//   Container Registry (ACR)            stores the ETL image
//   PostgreSQL Flexible Server          the analytics warehouse (Burstable, free-tier eligible)
//   Storage Account (ADLS Gen2)         Blob container for CSV snapshots / lineage
//   Log Analytics + Container Apps env  logs + serverless runtime
//   Container Apps Job (cron)           runs extract -> transform -> load @monthly
//   User-assigned managed identity      pulls from ACR and writes to Blob without secrets
//
// The Container Apps *Job* is the cloud equivalent of the Airflow @monthly DAG:
// it wakes on a schedule, runs the container once to completion, and shuts down.
//
// Deploy:
//   az group create -n rg-economic-indicators-etl -l eastus
//   az deployment group create -g rg-economic-indicators-etl \
//     -f infra/main.bicep -p infra/main.parameters.json \
//     -p pgAdminPassword='<strong-password>' -p imageTag=<git-sha>

targetScope = 'resourceGroup'

@description('Base name used to derive resource names. Lowercase letters and numbers only.')
@minLength(3)
@maxLength(11)
param namePrefix string = 'econetl'

@description('Azure region for all resources. Defaults to the resource group location.')
param location string = resourceGroup().location

@description('Container image tag to deploy — pass the git commit SHA from CI.')
param imageTag string = 'latest'

@description('PostgreSQL administrator login name.')
param pgAdminUser string = 'etladmin'

@description('PostgreSQL administrator password. Provide via a secret, never commit it.')
@secure()
@minLength(8)
param pgAdminPassword string

@description('Name of the application database created on the server.')
param pgDatabaseName string = 'economics'

@description('Cron schedule for the ETL job (UTC). Default: 00:00 on the 1st of each month.')
param cronExpression string = '0 0 1 * *'

// ---------------------------------------------------------------------------
// Derived names — globally-unique where the resource requires it.
// ---------------------------------------------------------------------------
var suffix = uniqueString(resourceGroup().id)
var acrName = toLower('${namePrefix}acr${suffix}')
var storageName = toLower('${namePrefix}st${suffix}')
var pgServerName = toLower('${namePrefix}-pg-${suffix}')
var lawName = '${namePrefix}-law-${suffix}'
var caeName = '${namePrefix}-cae-${suffix}'
var jobName = '${namePrefix}-etl-job'
var uamiName = '${namePrefix}-uami'
var blobContainerName = 'snapshots'

// Built-in role definition IDs.
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d' // AcrPull
var blobContributorRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe' // Storage Blob Data Contributor

// ---------------------------------------------------------------------------
// Identity — one user-assigned identity used for ACR pull and Blob writes,
// so no registry passwords or storage keys ever live in the job config.
// ---------------------------------------------------------------------------
resource uami 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: uamiName
  location: location
}

// ---------------------------------------------------------------------------
// Container registry
// ---------------------------------------------------------------------------
resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: acrName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
  }
}

resource acrPullAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, uami.id, acrPullRoleId)
  scope: acr
  properties: {
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
  }
}

// ---------------------------------------------------------------------------
// Storage (ADLS Gen2) — Blob container for exported CSV snapshots.
// ---------------------------------------------------------------------------
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    isHnsEnabled: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource snapshotsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: blobContainerName
}

resource blobContributorAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, uami.id, blobContributorRoleId)
  scope: storage
  properties: {
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobContributorRoleId)
  }
}

// ---------------------------------------------------------------------------
// PostgreSQL Flexible Server — the warehouse the pipeline loads into.
// ---------------------------------------------------------------------------
resource pg 'Microsoft.DBforPostgreSQL/flexibleServers@2023-06-01-preview' = {
  name: pgServerName
  location: location
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    version: '16'
    administratorLogin: pgAdminUser
    administratorLoginPassword: pgAdminPassword
    storage: {
      storageSizeGB: 32
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
  }
}

resource pgDb 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-06-01-preview' = {
  parent: pg
  name: pgDatabaseName
}

// Let other Azure services (the Container Apps job) reach the server.
resource pgFirewallAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2023-06-01-preview' = {
  parent: pg
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

// ---------------------------------------------------------------------------
// Logging + serverless runtime
// ---------------------------------------------------------------------------
resource law 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: lawName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource cae 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: caeName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: law.properties.customerId
        sharedKey: law.listKeys().primarySharedKey
      }
    }
  }
}

// SQLAlchemy URL the pipeline reads from DATABASE_URL. TLS required by Flexible Server.
var databaseUrl = 'postgresql+psycopg2://${pgAdminUser}:${pgAdminPassword}@${pg.properties.fullyQualifiedDomainName}:5432/${pgDatabaseName}?sslmode=require'

// ---------------------------------------------------------------------------
// The scheduled ETL job — the cloud-native replacement for the Airflow DAG.
// ---------------------------------------------------------------------------
resource job 'Microsoft.App/jobs@2024-03-01' = {
  name: jobName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${uami.id}': {}
    }
  }
  properties: {
    environmentId: cae.id
    configuration: {
      triggerType: 'Schedule'
      scheduleTriggerConfig: {
        cronExpression: cronExpression
        parallelism: 1
        replicaCompletionCount: 1
      }
      replicaTimeout: 1800
      replicaRetryLimit: 2
      registries: [
        {
          server: acr.properties.loginServer
          identity: uami.id
        }
      ]
      secrets: [
        {
          name: 'database-url'
          value: databaseUrl
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'econ-etl'
          image: '${acr.properties.loginServer}/econ-etl:${imageTag}'
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            {
              name: 'DATABASE_URL'
              secretRef: 'database-url'
            }
            {
              name: 'SNAPSHOT_ACCOUNT_URL'
              value: 'https://${storage.name}.blob.${environment().suffixes.storage}'
            }
            {
              name: 'SNAPSHOT_CONTAINER'
              value: blobContainerName
            }
            {
              name: 'AZURE_CLIENT_ID'
              value: uami.properties.clientId
            }
          ]
        }
      ]
    }
  }
}

// ---------------------------------------------------------------------------
// Outputs — consumed by the CI/CD workflow.
// ---------------------------------------------------------------------------
output acrName string = acr.name
output acrLoginServer string = acr.properties.loginServer
output jobName string = job.name
output resourceGroup string = resourceGroup().name
output pgFqdn string = pg.properties.fullyQualifiedDomainName
output storageAccount string = storage.name
output managedIdentityClientId string = uami.properties.clientId

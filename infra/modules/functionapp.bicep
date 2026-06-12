// Azure Functions (Flex Consumption) host for the County Assistant backend.
//
// This is the DEFAULT/recommended serverless compute for the government scenario:
// scale-to-zero between bursts of resident traffic. It runs the same shared
// orchestrator as the Container App option; only the hosting model differs.
//
// Security: the app runs under a user-assigned managed identity (AZURE_CLIENT_ID
// selects it for DefaultAzureCredential) and uses identity-based access to its
// own storage account — no connection-string secrets.
metadata description = 'Flex Consumption Function App hosting the County Assistant backend.'

@description('Azure region.')
param location string

@description('Flex Consumption plan name.')
param planName string

@description('Function App (site) name.')
param appName string

@description('Storage account name (3-24 lowercase alphanumeric).')
param storageAccountName string

@description('Resource ID of the user-assigned managed identity.')
param userAssignedIdentityId string

@description('Client ID of the user-assigned managed identity (for DefaultAzureCredential).')
param userAssignedClientId string

@description('Principal ID of the user-assigned managed identity (for RBAC).')
param principalId string

@description('Foundry project endpoint for AIProjectClient.')
param foundryProjectEndpoint string

@description('Model deployment name.')
param modelDeploymentName string

@description('Azure AI Search endpoint.')
param searchEndpoint string

@description('Azure AI Search index name.')
param searchIndex string

@description('Semantic ranker configuration name on the index.')
param searchSemanticConfig string = 'county-semantic'

@description('Embedding deployment name for hybrid retrieval.')
param embeddingDeploymentName string = 'text-embedding-3-small'

@description('Enable hybrid keyword+vector retrieval at query time.')
param vectorEnabled bool = true

@description('Application Insights connection string.')
param appInsightsConnectionString string = ''

@description('Python runtime version for the Flex Consumption app.')
param pythonVersion string = '3.12'

@description('Resource tags.')
param tags object = {}

// Built-in role: Storage Blob Data Owner (host + deployment storage via identity).
var storageBlobDataOwnerRoleId = 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
var deploymentContainerName = 'deployments'

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    // Flex Consumption pulls its deployment package from this account on every
    // cold start. Without VNet integration + a private endpoint, that access
    // uses the public endpoint, so it must remain enabled. The data plane stays
    // protected: shared keys are disabled (RBAC-only) and blob public access is
    // off. For a hardened deployment, add VNet integration + a private endpoint
    // and set this to 'Disabled'.
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Allow'
    }
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource deploymentContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: deploymentContainerName
  properties: {
    publicAccess: 'None'
  }
}

// Grant the app's identity blob data access (host storage + deployment package).
resource storageRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, principalId, storageBlobDataOwnerRoleId)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      storageBlobDataOwnerRoleId
    )
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: planName
  location: location
  tags: tags
  sku: {
    name: 'FC1'
    tier: 'FlexConsumption'
  }
  kind: 'functionapp'
  properties: {
    reserved: true
  }
}

resource site 'Microsoft.Web/sites@2023-12-01' = {
  name: appName
  location: location
  tags: tags
  kind: 'functionapp,linux'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${userAssignedIdentityId}': {}
    }
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${storage.properties.primaryEndpoints.blob}${deploymentContainerName}'
          authentication: {
            type: 'UserAssignedIdentity'
            userAssignedIdentityResourceId: userAssignedIdentityId
          }
        }
      }
      scaleAndConcurrency: {
        maximumInstanceCount: 100
        instanceMemoryMB: 2048
      }
      runtime: {
        name: 'python'
        version: pythonVersion
      }
    }
    siteConfig: {
      appSettings: [
        { name: 'AzureWebJobsStorage__accountName', value: storage.name }
        { name: 'AzureWebJobsStorage__credential', value: 'managedidentity' }
        { name: 'AzureWebJobsStorage__clientId', value: userAssignedClientId }
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsightsConnectionString }
        { name: 'APP_ENV', value: 'prod' }
        { name: 'APP_LOG_JSON', value: 'true' }
        { name: 'FOUNDRY_ENABLED', value: 'true' }
        { name: 'AZURE_AI_PROJECT_ENDPOINT', value: foundryProjectEndpoint }
        { name: 'AZURE_AI_MODEL_DEPLOYMENT', value: modelDeploymentName }
        { name: 'AZURE_SEARCH_ENDPOINT', value: searchEndpoint }
        { name: 'AZURE_SEARCH_INDEX', value: searchIndex }
        { name: 'AZURE_SEARCH_SEMANTIC_CONFIG', value: searchSemanticConfig }
        { name: 'AZURE_EMBEDDING_DEPLOYMENT', value: embeddingDeploymentName }
        { name: 'RAG_VECTOR_ENABLED', value: string(vectorEnabled) }
        { name: 'AZURE_CLIENT_ID', value: userAssignedClientId }
        { name: 'OTEL_ENABLED', value: 'true' }
      ]
    }
  }
  dependsOn: [
    storageRoleAssignment
  ]
}

output name string = site.name
output fqdn string = site.properties.defaultHostName

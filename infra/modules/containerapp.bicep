// Azure Container Apps host for the FastAPI backend (optional production path).
// The app runs under a user-assigned managed identity so it reaches Foundry and
// Azure AI Search without secrets (AZURE_CLIENT_ID selects the identity).
metadata description = 'Container Apps environment and app hosting the County Assistant backend.'

@description('Azure region.')
param location string

@description('Container Apps managed environment name.')
param environmentName string

@description('Container app name.')
param appName string

@description('Resource ID of the user-assigned managed identity.')
param userAssignedIdentityId string

@description('Client ID of the user-assigned managed identity (for DefaultAzureCredential).')
param userAssignedClientId string

@description('Container image reference (build and push before deploying).')
param containerImage string = 'mcr.microsoft.com/k8se/quickstart:latest'

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

@description('Resource tags.')
param tags object = {}

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: environmentName
  location: location
  tags: tags
  properties: {}
}

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${userAssignedIdentityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: environment.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
      }
    }
    template: {
      containers: [
        {
          name: 'county-assistant'
          image: containerImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
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
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsightsConnectionString }
            { name: 'OTEL_ENABLED', value: 'true' }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 3
      }
    }
  }
}

output name string = app.name
output fqdn string = app.properties.configuration.ingress.fqdn

// Azure AI Foundry account (kind: AIServices) + project + model deployment.
// The backend identity is granted Cognitive Services OpenAI User for inference.
metadata description = 'Azure AI Foundry account, project, model deployment, and RBAC for the backend identity.'

@description('Azure region.')
param location string

@description('Foundry (AI Services) account name.')
param accountName string

@description('Foundry project name.')
param projectName string

@description('Principal ID of the backend managed identity.')
param principalId string

@description('Model to deploy (OpenAI format).')
param modelName string = 'gpt-4o-mini'

@description('Model version.')
param modelVersion string = '2024-07-18'

@description('Deployment capacity (thousands of tokens per minute).')
param modelCapacity int = 20

@description('Embedding model to deploy for vector / hybrid retrieval.')
param embeddingModelName string = 'text-embedding-3-small'

@description('Embedding model version.')
param embeddingModelVersion string = '1'

@description('Embedding deployment capacity (thousands of tokens per minute).')
param embeddingCapacity int = 50

@description('Log Analytics workspace resource ID for Foundry account diagnostic logs (Audit, RequestResponse, Trace, AzureOpenAIRequestUsage). Leave empty to skip.')
param logAnalyticsId string = ''

@description('Application Insights resource ID to connect to the Foundry project for agent tracing / Control Plane observability. Leave empty to skip.')
param appInsightsId string = ''

@description('Application Insights connection string used for the project observability connection.')
param appInsightsConnectionString string = ''

@description('Resource tags.')
param tags object = {}

// Built-in role: Cognitive Services OpenAI User (runtime inference)
var openAiUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
// Built-in role: Foundry User (data-plane access to run prompt agents and tools
// such as Grounding with Bing Custom Search). This role was previously named
// "Azure AI User"; the rename did not change the role id. Do NOT use the
// "Azure AI Developer" role here — despite the name it targets Azure ML
// workspaces / Foundry hubs, not Foundry projects or hosted agents.
var foundryUserRoleId = '53ca6127-db72-4b80-b1b0-d745d6d5456d'

resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: accountName
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    // Enables Foundry projects under this account.
    allowProjectManagement: true
    customSubDomainName: toLower(accountName)
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: false
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: account
  name: projectName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {}
}

resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: account
  name: modelName
  sku: {
    name: 'GlobalStandard'
    capacity: modelCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: modelName
      version: modelVersion
    }
  }
}

// Embedding deployment for vector / hybrid retrieval. Deployments on a single
// account must be created serially, so this depends on the chat deployment.
// GlobalStandard is used (rather than Standard) because Standard embedding quota
// is constrained in several regions; GlobalStandard has ample headroom.
resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: account
  name: embeddingModelName
  dependsOn: [
    modelDeployment
  ]
  sku: {
    name: 'GlobalStandard'
    capacity: embeddingCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: embeddingModelName
      version: embeddingModelVersion
    }
  }
}

resource openAiUserAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(account.id, principalId, openAiUserRoleId)
  scope: account
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      openAiUserRoleId
    )
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

// Foundry User at the project scope lets the backend identity run prompt agents
// and tools such as Grounding with Bing Custom Search (Patterns 1 and 3).
// Creating the Bing grounding *connection* and publishing a new agent version
// requires the Foundry Project Manager role (eadc314b-1a2d-4efa-be10-5d325db5065e),
// granted to the provisioning principal — see docs/retrieval-patterns.md.
resource foundryUserAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(project.id, principalId, foundryUserRoleId)
  scope: project
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      foundryUserRoleId
    )
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

// Platform diagnostic settings -> Log Analytics for the Foundry account. Surfaces
// request/response, audit, trace, and Azure OpenAI usage logs (feeds Control Plane
// observability and supports cost/usage analysis alongside the gateway logs).
resource foundryDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (!empty(logAnalyticsId)) {
  name: 'foundry-to-law'
  scope: account
  properties: {
    workspaceId: logAnalyticsId
    logs: [
      {
        category: 'Audit'
        enabled: true
      }
      {
        category: 'RequestResponse'
        enabled: true
      }
      {
        category: 'Trace'
        enabled: true
      }
      {
        category: 'AzureOpenAIRequestUsage'
        enabled: true
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
      }
    ]
  }
}

// Application Insights connection on the Foundry project. This is what lights up
// the project Tracing / Monitoring tab and feeds the Foundry Control Plane
// Overview/Assets health and continuous-evaluation experiences.
resource appInsightsConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = if (!empty(appInsightsId) && !empty(appInsightsConnectionString)) {
  parent: project
  name: 'appinsights'
  properties: {
    category: 'AppInsights'
    target: appInsightsId
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: {
      key: appInsightsConnectionString
    }
    metadata: {
      ApiType: 'Azure'
      ResourceId: appInsightsId
    }
  }
}

output accountName string = account.name
output accountEndpoint string = account.properties.endpoint
output projectName string = project.name
// Endpoint consumed by azure-ai-projects AIProjectClient(endpoint=...)
output projectEndpoint string = 'https://${account.name}.services.ai.azure.com/api/projects/${project.name}'
output modelDeploymentName string = modelDeployment.name
output embeddingDeploymentName string = embeddingDeployment.name

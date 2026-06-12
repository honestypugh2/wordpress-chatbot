// Azure AI Search service for RAG. Supports managed-identity (RBAC) and key auth.
// The backend identity is granted Search Index Data Reader for query-time access.
metadata description = 'Azure AI Search service with semantic ranking and RBAC for the backend identity.'

@description('Azure region.')
param location string

@description('Search service name (2-60 lowercase alphanumerics and hyphens).')
param name string

@description('Principal ID of the backend managed identity.')
param principalId string

@description('''Optional principal ID granted Search Index Data Contributor for
ingestion (create index + upload chunks). Leave empty to skip. Set to the
developer/CI principal that runs scripts/index_kb_to_search.py, or to principalId
if the indexing job runs in Azure under the managed identity. The runtime identity
above stays read-only (least privilege).''')
param indexAdminPrincipalId string = ''

@description('Principal type for indexAdminPrincipalId (User for a developer, ServicePrincipal for MI/CI).')
@allowed([
  'User'
  'ServicePrincipal'
])
param indexAdminPrincipalType string = 'User'

@description('Search SKU.')
@allowed([
  'basic'
  'standard'
  'standard2'
  'standard3'
])
param sku string = 'basic'

@description('Resource tags.')
param tags object = {}

// Built-in role: Search Index Data Reader (query-time document access)
var searchIndexDataReaderRoleId = '1407120a-92aa-4202-b7e9-c0e197c71c8f'
// Built-in role: Search Index Data Contributor (create index + upload documents)
var searchIndexDataContributorRoleId = '8ebe5a00-799e-43f5-93ac-243d3dce84a7'

resource search 'Microsoft.Search/searchServices@2024-06-01-preview' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: sku
  }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    semanticSearch: 'standard'
    publicNetworkAccess: 'enabled'
    // Allow both Microsoft Entra (RBAC) and API keys. Set disableLocalAuth: true
    // in hardened environments to force managed-identity-only access.
    disableLocalAuth: false
    authOptions: {
      aadOrApiKey: {
        aadAuthFailureMode: 'http403'
      }
    }
  }
}

resource indexDataReaderAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, principalId, searchIndexDataReaderRoleId)
  scope: search
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      searchIndexDataReaderRoleId
    )
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

// Write access for the ingestion/indexing principal (optional, least privilege:
// the runtime identity above remains read-only).
resource indexDataContributorAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(indexAdminPrincipalId)) {
  name: guid(search.id, indexAdminPrincipalId, searchIndexDataContributorRoleId)
  scope: search
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      searchIndexDataContributorRoleId
    )
    principalId: indexAdminPrincipalId
    principalType: indexAdminPrincipalType
  }
}

output id string = search.id
output name string = search.name
output endpoint string = 'https://${search.name}.search.windows.net'

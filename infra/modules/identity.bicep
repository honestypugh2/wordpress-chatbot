// User-assigned managed identity used by the backend to access Foundry, Search,
// and Key Vault without secrets.
metadata description = 'User-assigned managed identity for the County Assistant backend.'

@description('Azure region.')
param location string

@description('Name of the user-assigned managed identity.')
param name string

@description('Resource tags.')
param tags object = {}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: name
  location: location
  tags: tags
}

output id string = identity.id
output name string = identity.name
output clientId string = identity.properties.clientId
output principalId string = identity.properties.principalId

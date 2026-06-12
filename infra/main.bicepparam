using './main.bicep'

// Edit these for your environment, then deploy:
//   az deployment group create -g <rg> -f infra/main.bicep -p infra/main.bicepparam

param namePrefix = 'wpcounty'
param environmentName = 'dev'
// location defaults to the resource group's location; override if needed.
param apimPublisherEmail = 'cloud-team@westvale.example.gov'
param apimPublisherName = 'County of Westvale'
param apimSku = 'Developer'
param searchSku = 'basic'
param modelName = 'gpt-4o-mini'
param modelVersion = '2024-07-18'
param modelCapacity = 20
// Backend compute host:
//   'function'     → Azure Functions (Flex Consumption). Serverless, scale-to-zero. DEFAULT.
//   'containerapp' → Azure Container Apps (always-on FastAPI). Set backendImage first.
//   'none'         → No backend (APIM falls back to the raw Foundry endpoint).
param backendHost = 'function'
// Only used when backendHost = 'containerapp' (build & push the image first).
// param backendImage = '<your-registry>.azurecr.io/county-assistant:latest'

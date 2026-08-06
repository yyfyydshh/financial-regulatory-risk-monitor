# Enterprise profile fields

The profile is a fact set used only to test applicability. Empty fields are unknown, not negative facts.

## Core identity

- `company_name`: legal or demonstration name. Prefix synthetic names with “演示”.
- `company_type`: bank, insurer, consumer-finance company, financing guarantee company, technology service provider, intermediary, or another explicit type.
- `operating_regions`: registered, licensed, branch, customer-service, and online-business regions.
- `licensed_activities`: license type, issuing authority, permitted scope, and status when known.

## Business exposure

- `products_and_services`: lending, deposits, insurance, payment support, wealth distribution, guarantees, collections, technology outsourcing, or other services.
- `customer_types`: consumers, small businesses, financial institutions, vulnerable groups, or other segments.
- `sales_channels`: branch, website, app, call center, agent, broker, platform, or partner channel.
- `partner_and_intermediary_types`: distributors, agents, brokers, collection vendors, data providers, cloud providers, and lead-generation partners.

## Control exposure

- `consumer_protection_exposure`: marketing, disclosure, suitability, complaints, pricing, collections, personal-information handling, and vulnerable-customer treatment.
- `data_processing_activities`: personal information, financial-account data, credit data, automated decisions, cross-border transfer, retention, and sharing.
- `technology_outsourcing`: cloud, core systems, model services, operations support, cybersecurity, and subcontracting.
- `anti_money_laundering_exposure`: onboarding, customer due diligence, beneficial ownership, transaction monitoring, suspicious-transaction reporting, sanctions screening, and record retention.
- `governance_features`: board oversight, three lines, compliance review, internal audit, issue remediation, regulatory reporting, and accountability.

## Evidence discipline

For every finding, list the exact matched fields and values. If a trigger fact is absent, lower applicability confidence or move the item to `pending_verification`; never fill a production fact by assumption. For synthetic demos, retain `synthetic_basis` entries that identify which collected themes motivated each invented attribute.

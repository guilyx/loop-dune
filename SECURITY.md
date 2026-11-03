# Security policy

## Reporting a vulnerability

Please **do not open a public issue**. Report it privately through GitHub:
**Security → Report a vulnerability** on the repository
([direct link](https://github.com/guilyx/loopscan/security/advisories/new)).

Include what is affected, how to reproduce it, and the impact you expect. You will get
an acknowledgement within a few days and a fix or a plan as soon as it is understood.

## Scope

In scope: the indexer, the dashboard and its API, the SQL migrations, the deploy and
backup scripts, and the GitHub workflows in this repository.

Out of scope: Loop Protocol's smart contracts (this project only reads them), and
third-party services (RPC providers, Dune, Supabase, Vercel).

## How the project protects itself

* Secrets live only in environment variables and GitHub secrets; nothing is committed.
* The dashboard connects with a read-only database role.
* Backups are encrypted to public keys; the private key never sits on the server.
* Dependencies are updated by Dependabot and scanned by CodeQL.

# SolviTask MVP — Odoo 17

**New in 17.0.3.0.0:** customer Draft → Submitted service intake creates a linked job. Read `UPDATE_SERVICE_REQUESTS.md` for the workflow and the exact changed files.

This revision implements Manager, Customer and Plumber as **internal users**.

## Access policy

| Area | Customer | Plumber | Manager |
| --- | --- | --- | --- |
| Service requests | Own drafts; submit to create job; submitted snapshot locked | No access | View all; can submit on behalf of customers |
| Customer profiles | Own profile, read only | Profiles of customers on assigned jobs; birthday and login hidden | All; manage |
| Jobs | Own only; read only; created by submitting a service request | Assigned only; update work notes and hours | All; manage assignments, prices, materials, stages |
| Plumber profiles | Name, surname, phone, email of plumbers assigned to own jobs | Own and co-assigned plumbers: name, surname, phone, email | All fields; manage |
| Plumber finances, home address, skills, availability, profile job/request lists, linked login | Hidden | Hidden, including own private fields in this MVP | Full access |
| Change requests | Own, against own jobs; edit draft and submit | Own, against assigned jobs; edit draft and submit | View all; approve/reject submitted requests |
| Catalogs | Read | Read | Manage |
| Materials used on jobs | Read own job lines | Read assigned job lines; request additions | Manage |
| Standard Contacts/Users directory | Own contact/login and company contacts only | Own contact/login and company contacts only | Existing Odoo access applies |

Co-assignment means a current database assignment on the same job, including closed jobs. Removing the shared assignment revokes visibility. Audit metadata such as record IDs is still available; protected business fields are enforced by Python field groups, not just hidden in forms. Job totals remain visible to the customer and assigned plumbers. Rates and bank details on plumber profiles are manager-only. Work notes are for plumbers/managers.

## Findings addressed

- The original ACLs granted broad create/write/delete rights, without any record rules.
- Plumber privacy used negative field groups and left hourly rates exposed.
- Readonly fields and hidden buttons were not server-side authorization checks.
- Requests could be forged with another requester or an already-approved initial state.
- Customers could change assignment, customer, price or stage through RPC.
- Missing catalog, material-line and availability ACLs caused ordinary access failures.
- Customer creation referenced ValidationError without importing it.
- New users inherited default groups through additive group commands. New logins now receive exactly the internal group and their SolviTask role, plus implied groups.
- Plumber home addresses are no longer copied into standard Contacts by account provisioning.
- Scheduling a New job through onchange conflicted with creation requiring New; scheduling is now an explicit manager action.

## Install or upgrade

1. Back up the database. Extract this archive into your configured custom addons directory, so the module is `custom_addons/solvitask/__manifest__.py`. Replace the existing module directory rather than nesting another copy inside it.
2. Stop the running Odoo service before upgrading from the terminal.
3. Run with your actual executable, configuration and database:

   ```bash
   /path/to/odoo-bin -c /path/to/odoo.conf -d YOUR_DATABASE -u solvitask --stop-after-init
   ```

   For a first installation, use `-i solvitask` instead of `-u solvitask`.
4. Start Odoo again. Assign your operator **SolviTask / Manager** in Settings → Users → Access Rights. The system administrator can assign this role.
5. Managers create customers and plumbers inside SolviTask. Each profile automatically creates its own internal login from the email address. Use Settings → Users to set a password or send a password reset invitation if outgoing email is configured. Account creation itself does not send an invitation.
6. Use separate logins to verify the access matrix; administrator/superuser access bypasses normal restrictions.

**Existing accounts:** the upgrade migration removes additional application/administration groups from customer/plumber logins and retains their internal SolviTask role. Manager access stays unchanged. If a user has more than one SolviTask role, the upgrade stops and rolls back: fix that user's roles and run the upgrade again. Do not combine customer/plumber roles with sales, accounting, settings or other application permissions. These MVP logins deliberately cannot be repurposed as general staff accounts. If you previously shared the same login between multiple customer or plumber profiles, resolve that duplication before upgrading because the new unique constraints require one profile per login per model.

New profile creation requires a new email/login; this revision does not include a wizard to attach pre-existing logins. Existing profile links remain intact. No data records or jobs are deleted by this revision.

## Verification

Python syntax, XML parsing, manifest data files, ACL model/group references, and view field references and modifier field availability were checked locally. **Odoo and PostgreSQL are unavailable in the build environment, so installation, view compilation and integration tests have not been run.** Test on an Odoo 17 staging database before production.

The included `tests/test_security.py` exercises internal account groups, customer isolation, direct read/write attempts, peer field privacy, assignment revocation, request spoofing/self-approval, core directory isolation, and incompatible role groups. Run on a disposable test database:

```bash
/path/to/odoo-bin -c /path/to/odoo.conf -d SOLVITASK_TEST_DB -i solvitask \
  --test-enable --test-tags /solvitask --stop-after-init
```

The intended environment is a dedicated MVP database. Record rules also restrict standard Contacts and Users for these two roles, so other installed apps may need separate integration work. Other third-party modules, custom controllers, existing public attachment shares, or code that deliberately uses sudo require their own audit; this module cannot revoke independently issued public links. The existing invoice output is a simple PDF job summary, not a posted accounting invoice.

## Odoo reference

https://www.odoo.com/documentation/17.0/developer/tutorials/restrict_data_access.html

## View installation fix

The Job form includes an unrestricted hidden, readonly stage_id field so ribbon modifiers can validate for every user. Role-specific statusbars remain in place. Server-side permissions still control changes to stages.

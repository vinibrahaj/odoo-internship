# SolviTask — Plumbing & Heating Service Management for Odoo 17

SolviTask is a custom Odoo 17 module for running a small plumbing and heating business. Customers submit service requests, managers turn them into jobs and assign plumbers, plumbers log their work, and every job moves through a clear pipeline from *New* to *Paid & Closed*.

It was built as an internship project and is intended for a dedicated Odoo database.

---

## Features

- **Customer service requests** — customers describe the problem, pick a service (or "Other"), add a photo, the building type and the job address. Submitting a request automatically creates a linked job, and the submitted request is locked.
- **Job management** — jobs have a priority (Low, Normal, High, Emergency), assigned plumbers, materials used, work notes and hours, and a Kanban pipeline:

  `New Jobs → In Progress → Ready to Invoice → Invoiced → Paid & Closed` (or `Canceled`)

  Stage changes follow fixed allowed transitions and are enforced on the server.
- **Change requests** — customers and plumbers can ask the manager for a reschedule, extra materials, a custom diagnosis, or a scope/price adjustment. The manager approves or rejects them.
- **Plumber profiles** — contact details, skills, weekly availability slots, payment method and bank details (manager-only).
- **Catalogs** — services, tools, and materials/parts with units (unit, meter, kg, liter).
- **WhatsApp button** — open a WhatsApp chat with a customer or plumber directly from their profile.
- **Job invoice report** — a printable PDF job summary (not a posted accounting invoice).
- **Automatic logins** — creating a customer or plumber profile creates their Odoo login from their email address, with exactly the right role.

## User roles

SolviTask has three roles, all implemented as internal Odoo users:

| Role | What they can do |
| --- | --- |
| **Manager** | Sees and manages everything: customers, plumbers, jobs, prices, stages, catalogs, and approval of change requests. |
| **Customer** | Creates and submits their own service requests, views their own jobs (read only), and sends change requests on them. |
| **Plumber** | Sees only jobs assigned to them, updates work notes and hours, requests materials, and sends change requests. |

Private data, such as plumber rates, bank details and home addresses, is restricted on the server through field groups and record rules, not just hidden in the forms. The full access matrix and security details are in [`SECURITY.md`](SECURITY.md).

## Project structure

```
odoo-internship/
├── .devcontainer/          # GitHub Codespaces / Docker setup
│   ├── devcontainer.json
│   ├── docker-compose.yml
│   └── odoo.conf
└── custom/                 # The Odoo module (installed as "solvitask")
    ├── __manifest__.py
    ├── models/             # Customer, plumber, job, service, request models
    ├── views/              # Forms, lists, Kanban and menus
    ├── security/           # Groups, record rules, access rights
    ├── report/             # Job invoice PDF
    ├── static/src/         # Backend SCSS and JS
    ├── migrations/         # Upgrade scripts
    └── tests/              # Security and service-request tests
```

> **The module folder must be named `solvitask` inside Odoo's addons path**, because the manifest loads its assets from `solvitask/static/...`. The Docker setup mounts `custom/` as `/mnt/extra-addons/solvitask` for you.

## Running it in GitHub Codespaces

1. Open the repository on GitHub and choose **Code → Codespaces → Create codespace**.
2. The containers start automatically. To start them by hand, run:

   ```bash
   docker compose -f .devcontainer/docker-compose.yml up -d
   ```

3. In the **Ports** tab, make sure port **8069** uses the **HTTP** protocol (right-click → *Change Port Protocol*), then open its link.
4. Create a database in the database manager. The master password is `admin`, as set in `.devcontainer/odoo.conf`.
5. Log in, enable **developer mode**, go to **Apps → Update Apps List**, search for **SolviTask** and install it.
6. In **Settings → Users**, give your user the **SolviTask / Manager** role.

### Useful commands

Upgrade the module after code changes. Replace `YOUR_DB` with your database name:

```bash
docker compose -f .devcontainer/docker-compose.yml exec odoo \
  odoo -c /etc/odoo/odoo.conf -d YOUR_DB -u solvitask --stop-after-init --no-http
docker compose -f .devcontainer/docker-compose.yml restart odoo
```

View the Odoo logs:

```bash
docker compose -f .devcontainer/docker-compose.yml logs -f odoo
```

### Codespaces notes

- Odoo shares PostgreSQL's network (`network_mode: "service:db"`) and connects to the database at `localhost`. This avoids a container-to-container networking issue with Docker inside Codespaces.
- The Odoo container starts Odoo directly instead of using the image's startup script, whose database check hung in Codespaces.
- Data is kept in Docker volumes while the codespace exists. Deleting the codespace deletes the test data.

## Installing on a regular Odoo server

1. Copy the `custom/` folder into your addons directory and rename it to `solvitask`, so you have `addons/solvitask/__manifest__.py`.
2. Install it:

   ```bash
   odoo-bin -c /path/to/odoo.conf -d YOUR_DB -i solvitask --stop-after-init
   ```

   For an upgrade, use `-u solvitask` instead of `-i solvitask`. Back up the database first.
3. Start Odoo and assign the **SolviTask / Manager** role to your operator user.

## Running the tests

The tests cover role isolation, field privacy, request spoofing, assignment revocation and the service-request workflow. Always run them on a throwaway database:

```bash
docker compose -f .devcontainer/docker-compose.yml exec odoo \
  odoo -c /etc/odoo/odoo.conf -d solvitask_test -i solvitask \
  --test-enable --test-tags /solvitask --stop-after-init --no-http
```

## Getting started as a manager

1. Fill in the catalogs: **services**, **tools** and **materials**.
2. Create **plumber** profiles with their weekly availability. Each profile gets its own login.
3. Create **customer** profiles. Each customer gets a login and can then submit service requests.
4. When a request comes in, open the created job, assign plumbers, schedule it, and move it through the stages.
5. Review incoming **change requests** and approve or reject them.

Administrator and superuser accounts bypass the normal access rules, so test each role with its own separate login.

## Requirements

- Odoo 17.0 (Community), depending only on `base` and `web`
- PostgreSQL 12 or newer (the Docker setup uses PostgreSQL 15)

## Disclaimer

SolviTask is an MVP. The included PDF is a job summary, not an accounting invoice, and the module's record rules also restrict the standard Contacts and Users directories for customers and plumbers. Other installed apps may therefore need extra integration work.

# CLAUDE.md - AI Assistant Guide for Research Repository

**Repository**: Research
**Last Updated**: 2026-11-17
**Status**: Active — several independent research projects

## Table of Contents
- [Repository Overview](#repository-overview)
- [Codebase Structure](#codebase-structure)
- [Development Workflows](#development-workflows)
- [Key Conventions](#key-conventions)
- [AI Assistant Guidelines](#ai-assistant-guidelines)
- [Technology Stack](#technology-stack)
- [Common Tasks](#common-tasks)

---

## Repository Overview

### Purpose
This is a research repository for experimental projects, proof-of-concepts, and learning exercises. The repository is designed to be flexible and accommodate various types of research work.

### Current State
- **Status**: Holds several self-contained project folders (see Directory Layout)
- **Branch Strategy**: Feature branches prefixed with `claude/`
- **Main Branch**: To be determined (typically `main` or `master`)

---

## Codebase Structure

### Directory Layout
```
Research/
├── CLAUDE.md                 # This file - AI assistant guidelines
├── README.md                 # Repository readme
├── index.html                # Root landing page
├── .gitignore
├── VAR/                      # Brown's three VaR backtests on the NASDAQ: site and independent check (see below)
├── baseball_var/             # Project folder
├── bets/                     # Shared log of the user's actual bets, every sport (see below)
├── expense/                  # Personal cash-flow Streamlit app on bank exports (see below)
├── golf/                     # Project folder
├── hurling/                  # GAA hurling Team/Hurler of the Week app (see below)
├── kelly_sim/                # Project folder
├── march_madness/            # Project folder
├── nfl_report/               # NFL five-factor system: site, bet ledger, weekly routine (see below)
├── premier_league_handicap/  # Handicap-adjusted Premier League: site and weekly routine (see below)
└── rugby_urc/                # URC five-factor handicap system: site, app, weekly routine (see below)
```

**Note**: As the repository grows, update this section to reflect the actual structure.

### Key Directories
- **`hurling/`** — static, mobile-first app for the 2026 GAA.ie Hurling Team of the Week and
  Hurler of the Week. Data lives in `hurling/data/*.json`; `index.html` renders it.
  After any data or `index.html` change, run `python3 build_standalone.py` inside `hurling/`
  to regenerate `standalone.html` (the copy behind the shareable link). See `hurling/README.md`.
- **`expense/`** — Streamlit app (`finance_cash.py`) analysing Visa and current account bank
  exports. The repo is public, so **never commit real bank data**: the user's exports, mapping and
  balances live outside the repo, and only the generated `sample_data/` is tracked (`.gitignore`
  enforces this). Regenerate sample data with `python3 generate_sample_data.py`; run
  `pytest test_finance.py` inside `expense/`. See `expense/README.md`.
- **`rugby_urc/`** — the URC five-factor against-the-spread system, run weekly through the
  2026-27 season. Each week: reconcile and load the scraped round (`import_turnovers.py`), the
  user's entry sheet (`entry_sheet.py import`), then run `season_report.py`, `shadow_factors.py`,
  `spot_check.py draw`, `build_site.py` (the GitHub Pages `index.html`) and
  `entry_sheet.py export`. Then run `python3 test_independent.py`, which must end "all checks
  passed": it recomputes every published figure (report, shadow votes, site, bet tracker)
  **without importing the pipeline**; keep it that way. `python3 test_pipeline.py` checks the
  plumbing on generated data. See `rugby_urc/README.md`, *Each week* and *Tests*.
  **Before setting up 2027-28**, ask the user whether the power factor keeps its rule or switches
  to the 3-point version (shadow factor `power_3`), then move `POWER_RULE_DECIDED_FOR` in
  `season_report.py` on; `season_report.py`, `import_fixtures.py` and the site raise it once the
  new season's fixtures are loaded. Past picks are not frozen, by the user's choice: the bet log
  is the record of what was bet, and any rule change is written up in the README.
- **`bets/`** — `bet_log.csv`, the user's actual bets in every sport, one row per bet. Public, and
  read by `rugby_urc/my_bets.py`. Ids are never reused; special offers are left out. See
  `bets/README.md`.
- **`nfl_report/`** — Aaron Brown's NFL five-factor against-the-spread system: the 2010-16
  replication plus seasons generated from raw data, run weekly through 2026-27. Each week: load
  the user's pro-football-reference rows into `data/results_2026.csv` **before** refreshing lines
  (a game's line freezes once it is played), save the nflverse export as `data/schedule_lines.csv`,
  then run `enrich_odds.py`, `season_report.py`, `build_site.py` (the GitHub Pages `index.html`)
  and `ledger.py`. The user logs bets in a claude.ai ledger page (`ledger.html`); they are copied
  to `data/my_bets_2026.csv`, public by the user's choice, with bonus bet builders left out.
  `bets/bet_log.csv` is not read. See `nfl_report/README.md`, *Updating the season in progress*.
- **`premier_league_handicap/`** — the Premier League table re-scored with the user's
  pre-season handicaps (earned pro rata: handicap × played / 38), plus Asian handicap covers
  and win-and-draw bets. Published as a GitHub Pages site and updated weekly through 2026-27.
  Each week:
  - write the user's FBref paste to `data/2026_2027/results.csv`;
  - save their football-data export as `data/2026_2027/football_data.csv`;
  - run `python3 build_site.py`;
  - run `python3 test_pipeline.py`, which must end "All checks passed".

  The test recomputes every published figure **without importing the pipeline**. Keep it that
  way: a shared-code check once passed a day/month transposition. See
  `premier_league_handicap/README.md`.
- **`VAR/`** — Aaron Brown's VaR article (*Forced by the Sternest Circumstances*, Wilmott
  2009): three daily 99% VaR methods on the NASDAQ Composite, each scored against his three
  backtests. Published as a GitHub Pages site. After any change to the data,
  `var_backtest.py` or `template.html`:
  - run `python3 build_site.py` (the report, the charts and `index.html`, in one go);
  - run `python3 test_pipeline.py`, which must end "All checks passed";
  - run `python3 test_pipeline.py --self-test`, which must catch every planted fault.

  The test recomputes every published figure from the raw CSV with the standard library
  alone and **never imports the pipeline**. Keep it that way. The historical-simulation
  percentile follows the article's rank rule, `p × (n + 1)`, not numpy's default: the
  default breaks on 1.12% of ideal days and once overstated that method's failure, and a
  check built on the same numpy call would have agreed with it. See `VAR/README.md`.
- _Other project folders: document here when they are next worked on._

---

## Development Workflows

### Git Workflow

#### Branch Naming Convention
- **Feature branches**: `claude/<descriptive-name>-<session-id>`
- **Bug fixes**: `fix/<issue-description>`
- **Experiments**: `experiment/<name>`
- **Documentation**: `docs/<description>`

#### Commit Message Guidelines
Follow conventional commit format:
```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks
- `perf`: Performance improvements

**Example**:
```
feat(analysis): add data preprocessing pipeline

Implemented a new preprocessing pipeline that handles:
- Data cleaning and validation
- Feature extraction
- Normalization

Closes #123
```

#### Working with Branches

1. **Create a new branch**:
   ```bash
   git checkout -b claude/<feature-name>-<session-id>
   ```

2. **Make changes and commit**:
   ```bash
   git add .
   git commit -m "descriptive message"
   ```

3. **Push to remote**:
   ```bash
   git push -u origin claude/<feature-name>-<session-id>
   ```

4. **Create Pull Request**:
   ```bash
   gh pr create --title "Title" --body "Description"
   ```

### Development Process

1. **Before Starting Work**:
   - Read relevant documentation
   - Understand the task requirements
   - Check for existing related code
   - Plan the implementation approach

2. **During Development**:
   - Write clean, maintainable code
   - Follow existing code style
   - Add comments for complex logic
   - Write tests for new functionality
   - Keep commits atomic and focused

3. **Before Committing**:
   - Review all changes
   - Run tests (if available)
   - Check for unintended modifications
   - Ensure code follows conventions

4. **Code Review**:
   - Provide clear PR descriptions
   - Respond to feedback constructively
   - Make requested changes promptly

---

## Key Conventions

### Code Style

#### General Principles
- **Clarity over cleverness**: Write code that's easy to understand
- **Consistency**: Follow existing patterns in the codebase
- **Simplicity**: Avoid over-engineering
- **Documentation**: Comment complex logic, document public APIs

#### Naming Conventions
- **Variables/Functions**: Use descriptive names in camelCase or snake_case (depending on language)
- **Classes**: PascalCase
- **Constants**: UPPER_SNAKE_CASE
- **Files**: kebab-case for scripts, match language conventions for source files

#### File Organization
- Group related functionality together
- Keep files focused and reasonably sized
- Use clear, descriptive file names
- Maintain consistent directory structure

### Documentation Standards

#### Code Comments
- Use inline comments sparingly, only for complex logic
- Keep comments up-to-date with code changes
- Explain "why", not "what" (code should be self-explanatory for "what")

#### Documentation Files
- Keep README.md updated with project overview and setup instructions
- Document APIs and public interfaces
- Include examples and usage guidelines
- Maintain a CHANGELOG for significant changes

### Testing Guidelines
_To be defined based on project needs_

---

## AI Assistant Guidelines

### General Behavior

#### DO:
- ✅ Read files before modifying them
- ✅ Use TodoWrite tool for multi-step tasks
- ✅ Follow existing code patterns and conventions
- ✅ Make minimal, focused changes
- ✅ Test changes when possible
- ✅ Provide clear commit messages
- ✅ Ask for clarification when requirements are unclear
- ✅ Document significant changes
- ✅ Use appropriate tools for each task (Read, Edit, Write, Bash)
- ✅ Search for existing implementations before creating new ones

#### DON'T:
- ❌ Make changes to files you haven't read
- ❌ Add unnecessary features or refactoring
- ❌ Create files without necessity
- ❌ Use bash commands for file operations (use Read/Edit/Write tools)
- ❌ Skip error handling for user-facing code
- ❌ Commit without understanding what changed
- ❌ Push to wrong branches
- ❌ Add backwards-compatibility hacks unless required
- ❌ Over-engineer simple solutions

### Task Management

1. **For complex tasks** (3+ steps):
   - Use TodoWrite tool to create task list
   - Break down into manageable steps
   - Mark tasks in_progress before starting
   - Mark completed immediately after finishing

2. **For simple tasks** (1-2 steps):
   - Execute directly without TodoWrite
   - Keep implementation focused

### Code Modification Guidelines

#### Reading Code
```
1. Use Read tool to view the file
2. Understand the context and existing patterns
3. Identify what needs to change
4. Plan the modification approach
```

#### Editing Code
```
1. Use Edit tool for precise changes
2. Preserve existing formatting and style
3. Keep changes minimal and focused
4. Verify the change makes sense in context
```

#### Creating New Files
```
1. Only create when absolutely necessary
2. Follow project structure conventions
3. Use appropriate file naming
4. Include necessary documentation
```

### Git Operations

#### Committing Changes
- Only commit when explicitly requested or task is complete
- Review changes with `git status` and `git diff`
- Write meaningful commit messages following conventions
- Never skip hooks or force operations without explicit permission

#### Pushing Changes
- Always push to the correct branch (usually claude/* branches)
- Use `-u` flag for first push: `git push -u origin <branch-name>`
- Retry up to 4 times with exponential backoff on network failures
- Never force push to main/master without explicit permission

#### Pull Requests
- Create clear, descriptive PR titles
- Include summary of changes in PR body
- Add test plan or verification steps
- Link related issues if applicable

### Security Considerations

Always be vigilant about:
- **Input validation**: Validate user inputs at system boundaries
- **SQL injection**: Use parameterized queries
- **XSS**: Sanitize user-generated content
- **Command injection**: Avoid shell execution with user input
- **Secrets**: Never commit API keys, passwords, or credentials
- **Dependencies**: Be aware of security vulnerabilities in packages

### Error Handling

- Add error handling at system boundaries (user input, external APIs, file I/O)
- Don't add excessive error handling for internal functions
- Trust framework and language guarantees
- Provide meaningful error messages to users
- Log errors appropriately for debugging

---

## Technology Stack

### Current Stack
_To be documented as technologies are added_

### Planned Technologies
_To be documented based on project direction_

### Development Tools
- Git for version control
- GitHub CLI (`gh`) for PR management
- _Additional tools to be added as needed_

---

## Common Tasks

### Setting Up Development Environment
```bash
# Clone the repository
git clone <repository-url>
cd Research

# Create and switch to development branch
git checkout -b claude/<feature-name>-<session-id>

# Install dependencies (when applicable)
# [To be documented based on project type]
```

### Running Tests
_To be documented when test framework is added_

### Building the Project
_To be documented when build process is established_

### Deployment
_To be documented when deployment process is established_

---

## Project-Specific Notes

### Research Areas
_Document specific research focuses, methodologies, or experimental approaches as they emerge_

### Experiment Tracking
_Document how experiments are tracked, results stored, and findings documented_

### Data Management
_Document data storage, processing pipelines, and data governance policies as needed_

---

## Maintenance

### Updating This Document
- Update CLAUDE.md whenever significant changes are made to:
  - Repository structure
  - Development workflows
  - Coding conventions
  - Technology stack
  - Common procedures

- Keep the "Last Updated" date current
- Document new patterns as they emerge
- Remove outdated information

### Regular Reviews
- Review this document quarterly or after major changes
- Ensure guidelines reflect current practices
- Update examples to match current codebase
- Solicit feedback from contributors

---

## Additional Resources

### Documentation
- [Git Documentation](https://git-scm.com/doc)
- [GitHub CLI Documentation](https://cli.github.com/manual/)
- _Add project-specific documentation links as they're created_

### Contact & Support
_To be documented: How to get help, who to contact for specific areas_

---

## Changelog

### 2026-11-17 - rugby_urc/ power rule
- Documented that the power rule is put to the user before 2027-28, and that picks are not frozen

### 2026-11-16 - Add VAR/
- Documented the VaR site's build, its independent check, and the percentile rule

### 2026-11-15 - rugby_urc/ independent check
- Documented `rugby_urc/test_independent.py`, run after every build

### 2026-11-09 - Add premier_league_handicap/
- Documented the weekly routine and its independent check, `test_pipeline.py`

### 2026-11-04 - Add nfl_report/
- Documented the NFL system's weekly routine and where its bets are kept

### 2026-10-31 - Add rugby_urc/ and bets/
- Documented the URC system's weekly routine and the shared bet log

### 2026-10-11 - Add expense/
- Documented `expense/` and its rule that no real bank data is committed

### 2026-10-10 - Reflect actual repository layout
- Replaced the placeholder directory layout with the real top-level folders
- Documented `hurling/` and its `build_standalone.py` regeneration step

### 2026-01-22 - Initial Creation
- Created comprehensive CLAUDE.md template
- Established basic structure and conventions
- Set up guidelines for AI assistants
- Defined git workflow and branching strategy

---

**Note to AI Assistants**: This document is a living guide. As you work with this repository, help keep it up-to-date by suggesting improvements and documenting new patterns. When in doubt, ask the user for clarification rather than making assumptions.

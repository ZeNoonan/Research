# CLAUDE.md - AI Assistant Guide for Research Repository

**Repository**: Research
**Last Updated**: 2026-01-22
**Status**: Initial Setup

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
- **Status**: Empty repository, ready for initial setup
- **Branch Strategy**: Feature branches prefixed with `claude/`
- **Main Branch**: To be determined (typically `main` or `master`)

---

## Codebase Structure

### Directory Layout
```
Research/
├── CLAUDE.md           # This file - AI assistant guidelines
├── README.md           # Project documentation (to be created)
├── .gitignore          # Git ignore patterns (to be created)
├── docs/               # Documentation directory (to be created)
├── src/                # Source code (to be created)
├── tests/              # Test files (to be created)
└── scripts/            # Utility scripts (to be created)
```

**Note**: As the repository grows, update this section to reflect the actual structure.

### Key Directories
_To be documented as the codebase develops_

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

### 2026-01-22 - Initial Creation
- Created comprehensive CLAUDE.md template
- Established basic structure and conventions
- Set up guidelines for AI assistants
- Defined git workflow and branching strategy

---

**Note to AI Assistants**: This document is a living guide. As you work with this repository, help keep it up-to-date by suggesting improvements and documenting new patterns. When in doubt, ask the user for clarification rather than making assumptions.

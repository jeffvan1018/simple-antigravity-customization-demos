---
name: dotnet-solution-scaffold
description: >-
  Scaffolds a standardized, production-ready .NET solution with src/ and test/ directories, Git repository initialization, .gitignore, clean architecture project references (Core class library, ASP.NET MVC, Web API), and an xUnit test project. Use whenever the user asks to create, initialize, or scaffold a new .NET / C# solution or project structure.
---

# .NET Solution Scaffolding Skill

This skill provides a standardized, repeatable procedure and automation script to scaffold production-ready .NET solutions with clean modular structure.

## Solution Architecture & Layout

The standard layout splits application code and tests into top-level directories:

```
<SolutionName>/
├── .gitignore
├── <SolutionName>.slnx (or .sln)
├── src/
│   ├── <SolutionName>.Core/       # Class Library (Domain, Entities, Contracts)
│   ├── <SolutionName>.Web/        # ASP.NET Core MVC Web Application
│   └── <SolutionName>.Api/        # ASP.NET Core Web API
└── test/
    └── <SolutionName>.Tests/      # xUnit Test Project (references Core, Web, Api)
```

### Dependency Rules:
- **Core (`<SolutionName>.Core`)**: Has no dependencies on Web or API.
- **Web (`<SolutionName>.Web`)**: References `<SolutionName>.Core`.
- **Api (`<SolutionName>.Api`)**: References `<SolutionName>.Core`.
- **Tests (`<SolutionName>.Tests`)**: References `<SolutionName>.Core`, `<SolutionName>.Web`, and `<SolutionName>.Api`.

---

## Method 1: Using the Automated Scaffolding Script (Recommended)

Run the bundled executable script [scaffold-solution.sh](./scripts/scaffold-solution.sh):

```bash
# Basic usage in current directory:
~/.agents/skills/dotnet-solution-scaffold/scripts/scaffold-solution.sh <SolutionName>

# Specify a target directory:
~/.agents/skills/dotnet-solution-scaffold/scripts/scaffold-solution.sh <SolutionName> --dir /path/to/project

# Customize components or names:
~/.agents/skills/dotnet-solution-scaffold/scripts/scaffold-solution.sh <SolutionName> \
  --core-name Core \
  --web-name Web \
  --api-name Api \
  --test-name Tests
```

Available script options:
- `-d, --dir <path>`: Target directory (default: `.`)
- `--no-git`: Skip `git init` and `.gitignore`
- `--no-web`: Skip ASP.NET Core MVC project
- `--no-api`: Skip ASP.NET Core Web API project
- `--no-tests`: Skip xUnit test project
- `--core-name <name>`: Suffix/name for class library (default: `Core`)
- `--web-name <name>`: Suffix/name for web app (default: `Web`)
- `--api-name <name>`: Suffix/name for API (default: `Api`)
- `--test-name <name>`: Suffix/name for tests (default: `Tests`)

---

## Method 2: Manual Step-by-Step Procedure

If customization beyond the script is needed, follow these steps:

### 1. Git Initialization & Ignore File
```bash
git init -b main
dotnet new gitignore
```

### 2. Top-Level Directories & Solution File
```bash
mkdir -p src test
dotnet new sln -n <SolutionName>
```
*Note: In .NET 9+ / .NET 10, `dotnet new sln` creates `<SolutionName>.slnx` by default.*

### 3. Scaffold Projects
```bash
# Shared Class Library
dotnet new classlib -n <SolutionName>.Core -o src/<SolutionName>.Core

# ASP.NET Core MVC Web Application
dotnet new mvc -n <SolutionName>.Web -o src/<SolutionName>.Web

# ASP.NET Core Web API
dotnet new webapi -n <SolutionName>.Api -o src/<SolutionName>.Api

# xUnit Test Suite
dotnet new xunit -n <SolutionName>.Tests -o test/<SolutionName>.Tests
```

### 4. Configure Project References
```bash
# Web references Core
dotnet add src/<SolutionName>.Web/<SolutionName>.Web.csproj reference src/<SolutionName>.Core/<SolutionName>.Core.csproj

# Api references Core
dotnet add src/<SolutionName>.Api/<SolutionName>.Api.csproj reference src/<SolutionName>.Core/<SolutionName>.Core.csproj

# Tests references Core, Web, and Api
dotnet add test/<SolutionName>.Tests/<SolutionName>.Tests.csproj reference \
  src/<SolutionName>.Core/<SolutionName>.Core.csproj \
  src/<SolutionName>.Web/<SolutionName>.Web.csproj \
  src/<SolutionName>.Api/<SolutionName>.Api.csproj
```

### 5. Add Projects to Solution
Find the solution file (`<SolutionName>.slnx` or `<SolutionName>.sln`):
```bash
SLN_FILE=$(find . -maxdepth 1 \( -name "*.slnx" -o -name "*.sln" \) | head -n 1)

dotnet sln "$SLN_FILE" add \
  src/<SolutionName>.Core/<SolutionName>.Core.csproj \
  src/<SolutionName>.Web/<SolutionName>.Web.csproj \
  src/<SolutionName>.Api/<SolutionName>.Api.csproj \
  test/<SolutionName>.Tests/<SolutionName>.Tests.csproj
```

### 6. Build and Test Verification
```bash
dotnet build
dotnet test
```
Confirm build succeeds with 0 errors and all tests pass.

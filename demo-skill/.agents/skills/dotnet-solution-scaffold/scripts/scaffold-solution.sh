#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# scaffold-solution.sh
# General script to scaffold a standardized multi-project .NET solution
# ==============================================================================

function show_usage() {
    cat << EOF
Usage: $(basename "$0") <SolutionName> [options]

Arguments:
  <SolutionName>          Name of the solution (e.g. MyCompany.Ordering or DCC.ExpenseReports)

Options:
  -d, --dir <path>        Target directory (default: current directory)
  --no-git                Skip git repository initialization
  --no-web                Skip ASP.NET Core MVC project
  --no-api                Skip ASP.NET Core Web API project
  --no-tests              Skip xUnit test project
  --core-name <name>      Custom suffix/name for the class library (default: Core)
  --web-name <name>       Custom suffix/name for the web app (default: Web)
  --api-name <name>       Custom suffix/name for the API (default: Api)
  --test-name <name>      Custom suffix/name for the tests (default: Tests)
  -h, --help              Show this help message

Example:
  $(basename "$0") DCC.ExpenseReports
EOF
}

SOLUTION_NAME=""
TARGET_DIR="."
INIT_GIT=true
INCLUDE_WEB=true
INCLUDE_API=true
INCLUDE_TESTS=true
CORE_SUFFIX="Core"
WEB_SUFFIX="Web"
API_SUFFIX="Api"
TEST_SUFFIX="Tests"

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            show_usage
            exit 0
            ;;
        -d|--dir)
            TARGET_DIR="$2"
            shift 2
            ;;
        --no-git)
            INIT_GIT=false
            shift
            ;;
        --no-web)
            INCLUDE_WEB=false
            shift
            ;;
        --no-api)
            INCLUDE_API=false
            shift
            ;;
        --no-tests)
            INCLUDE_TESTS=false
            shift
            ;;
        --core-name)
            CORE_SUFFIX="$2"
            shift 2
            ;;
        --web-name)
            WEB_SUFFIX="$2"
            shift 2
            ;;
        --api-name)
            API_SUFFIX="$2"
            shift 2
            ;;
        --test-name)
            TEST_SUFFIX="$2"
            shift 2
            ;;
        -*)
            echo "Error: Unknown option $1" >&2
            show_usage
            exit 1
            ;;
        *)
            if [[ -z "$SOLUTION_NAME" ]]; then
                SOLUTION_NAME="$1"
                shift
            else
                echo "Error: Unexpected argument $1" >&2
                show_usage
                exit 1
            fi
            ;;
    esac
done

if [[ -z "$SOLUTION_NAME" ]]; then
    echo "Error: SolutionName is required." >&2
    show_usage
    exit 1
fi

mkdir -p "$TARGET_DIR"
cd "$TARGET_DIR"

echo "==> Scaffolding .NET Solution: $SOLUTION_NAME in $(pwd)"

# 1. Git Initialization & .gitignore
if [[ "$INIT_GIT" = true ]]; then
    if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        echo "--> Initializing git repository on branch main..."
        git init -b main
    else
        echo "--> Existing git repository detected."
    fi

    if [[ ! -f ".gitignore" ]]; then
        echo "--> Creating .gitignore for dotnet..."
        dotnet new gitignore
    fi
fi

# 2. Top-level directories
mkdir -p src test

# 3. Create Solution File
echo "--> Creating solution file..."
dotnet new sln -n "$SOLUTION_NAME" --force

# Find the generated solution file (.slnx or .sln)
SLN_FILE=""
if [[ -f "${SOLUTION_NAME}.slnx" ]]; then
    SLN_FILE="${SOLUTION_NAME}.slnx"
elif [[ -f "${SOLUTION_NAME}.sln" ]]; then
    SLN_FILE="${SOLUTION_NAME}.sln"
else
    # Fallback to any sln/slnx in current dir
    SLN_FILE=$(find . -maxdepth 1 \( -name "*.slnx" -o -name "*.sln" \) | head -n 1)
fi

echo "--> Solution file created: $SLN_FILE"

PROJECTS_TO_ADD=()

# 4. Create Core Class Library
CORE_PROJECT_NAME="${SOLUTION_NAME}.${CORE_SUFFIX}"
CORE_CSPROJ="src/${CORE_PROJECT_NAME}/${CORE_PROJECT_NAME}.csproj"
echo "--> Creating Class Library: $CORE_PROJECT_NAME..."
dotnet new classlib -n "$CORE_PROJECT_NAME" -o "src/$CORE_PROJECT_NAME"
PROJECTS_TO_ADD+=("$CORE_CSPROJ")

# 5. Create Web Project (ASP.NET Core MVC)
if [[ "$INCLUDE_WEB" = true ]]; then
    WEB_PROJECT_NAME="${SOLUTION_NAME}.${WEB_SUFFIX}"
    WEB_CSPROJ="src/${WEB_PROJECT_NAME}/${WEB_PROJECT_NAME}.csproj"
    echo "--> Creating ASP.NET MVC project: $WEB_PROJECT_NAME..."
    dotnet new mvc -n "$WEB_PROJECT_NAME" -o "src/$WEB_PROJECT_NAME"
    echo "--> Adding reference from $WEB_PROJECT_NAME to $CORE_PROJECT_NAME..."
    dotnet add "$WEB_CSPROJ" reference "$CORE_CSPROJ"
    PROJECTS_TO_ADD+=("$WEB_CSPROJ")
fi

# 6. Create Web API Project
if [[ "$INCLUDE_API" = true ]]; then
    API_PROJECT_NAME="${SOLUTION_NAME}.${API_SUFFIX}"
    API_CSPROJ="src/${API_PROJECT_NAME}/${API_PROJECT_NAME}.csproj"
    echo "--> Creating ASP.NET Web API project: $API_PROJECT_NAME..."
    dotnet new webapi -n "$API_PROJECT_NAME" -o "src/$API_PROJECT_NAME"
    echo "--> Adding reference from $API_PROJECT_NAME to $CORE_PROJECT_NAME..."
    dotnet add "$API_CSPROJ" reference "$CORE_CSPROJ"
    PROJECTS_TO_ADD+=("$API_CSPROJ")
fi

# 7. Create Tests Project (xUnit)
if [[ "$INCLUDE_TESTS" = true ]]; then
    TEST_PROJECT_NAME="${SOLUTION_NAME}.${TEST_SUFFIX}"
    TEST_CSPROJ="test/${TEST_PROJECT_NAME}/${TEST_PROJECT_NAME}.csproj"
    echo "--> Creating xUnit project: $TEST_PROJECT_NAME..."
    dotnet new xunit -n "$TEST_PROJECT_NAME" -o "test/$TEST_PROJECT_NAME"

    # Add references to all created application projects
    echo "--> Adding references to test project..."
    dotnet add "$TEST_CSPROJ" reference "$CORE_CSPROJ"
    if [[ "$INCLUDE_WEB" = true ]]; then
        dotnet add "$TEST_CSPROJ" reference "$WEB_CSPROJ"
    fi
    if [[ "$INCLUDE_API" = true ]]; then
        dotnet add "$TEST_CSPROJ" reference "$API_CSPROJ"
    fi
    PROJECTS_TO_ADD+=("$TEST_CSPROJ")
fi

# 8. Add all projects to Solution
echo "--> Registering projects into $SLN_FILE..."
dotnet sln "$SLN_FILE" add "${PROJECTS_TO_ADD[@]}"

# 9. Verify Solution Build & Test
echo "--> Verifying solution build..."
dotnet build "$SLN_FILE"

if [[ "$INCLUDE_TESTS" = true ]]; then
    echo "--> Verifying test run..."
    dotnet test "$SLN_FILE"
fi

echo "=============================================================================="
echo " Solution scaffolding complete for $SOLUTION_NAME!"
echo " Solution file: $SLN_FILE"
echo " Projects:"
for p in "${PROJECTS_TO_ADD[@]}"; do
    echo "   - $p"
done
echo "=============================================================================="

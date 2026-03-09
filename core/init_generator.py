"""
Init script generator for AutoDev.

Generates init.sh scripts for different project types.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class InitScriptGenerator:
    """
    Generates init.sh scripts for different project types.

    The init.sh script is responsible for:
    - Installing dependencies
    - Starting the development server
    - Running basic health checks
    """

    # Template for init.sh
    INIT_SCRIPT_TEMPLATE = """#!/bin/bash
# AutoDev Init Script
# Generated for {project_type} project

set -e

echo "========================================="
echo "AutoDev - Starting Development Server"
echo "========================================="
echo ""

{setup_commands}

echo ""
echo "Starting development server..."
{start_command}

"""

    @staticmethod
    def detect_project_type(project_path: Path) -> str:
        """
        Detect the project type based on files present.

        Returns:
            Project type string (node, python, rust, go, java, unknown).
        """
        project_path = Path(project_path)

        # Check for Node.js
        if (project_path / "package.json").exists():
            return "node"

        # Check for Python
        if (project_path / "pyproject.toml").exists():
            return "python"
        if (project_path / "requirements.txt").exists():
            return "python"
        if (project_path / "setup.py").exists():
            return "python"

        # Check for Rust
        if (project_path / "Cargo.toml").exists():
            return "rust"

        # Check for Go
        if (project_path / "go.mod").exists():
            return "go"

        # Check for Java
        if (project_path / "pom.xml").exists():
            return "java-maven"
        if (project_path / "build.gradle").exists() or (project_path / "build.gradle.kts").exists():
            return "java-gradle"

        # Check for Ruby
        if (project_path / "Gemfile").exists():
            return "ruby"

        # Check for PHP
        if (project_path / "composer.json").exists():
            return "php"

        return "unknown"

    @classmethod
    def generate(
        cls,
        project_path: Path,
        project_type: Optional[str] = None,
        port: int = 3000,
    ) -> str:
        """
        Generate an init.sh script for the project.

        Args:
            project_path: Path to the project.
            project_type: Optional project type override.
            port: Port to run the dev server on.

        Returns:
            The init.sh script content.
        """
        project_path = Path(project_path)
        project_type = project_type or cls.detect_project_type(project_path)

        logger.info(f"Generating init.sh for {project_type} project at {project_path}")

        generators = {
            "node": cls._generate_node,
            "python": cls._generate_python,
            "rust": cls._generate_rust,
            "go": cls._generate_go,
            "java-maven": cls._generate_java_maven,
            "java-gradle": cls._generate_java_gradle,
            "ruby": cls._generate_ruby,
            "php": cls._generate_php,
            "unknown": cls._generate_generic,
        }

        generator = generators.get(project_type, cls._generate_generic)
        return generator(project_path, port)

    @staticmethod
    def _generate_node(project_path: Path, port: int) -> str:
        """Generate init.sh for Node.js project."""
        package_json = project_path / "package.json"
        start_cmd = "npm run dev"
        dev_port = port

        # Try to read package.json to determine start command
        if package_json.exists():
            try:
                with open(package_json, "r") as f:
                    data = json.load(f)

                scripts = data.get("scripts", {})

                # Prefer dev, then start
                if "dev" in scripts:
                    start_cmd = "npm run dev"
                elif "start" in scripts:
                    start_cmd = "npm start"
                elif "serve" in scripts:
                    start_cmd = "npm run serve"

                # Check for framework-specific ports
                if "next" in json.dumps(data.get("dependencies", {})):
                    dev_port = 3000
                elif "vite" in json.dumps(data.get("devDependencies", {})):
                    dev_port = 5173

            except Exception as e:
                logger.warning(f"Could not parse package.json: {e}")

        return f"""#!/bin/bash
# AutoDev Init Script for Node.js
# Generated automatically by AutoDev

set -e

echo "========================================="
echo "AutoDev - Starting Node.js Development"
echo "========================================="
echo ""

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    echo "Installing dependencies..."
    npm install
fi

# Start development server
echo ""
echo "Starting development server on port {dev_port}..."
{start_cmd}

"""

    @staticmethod
    def _generate_python(project_path: Path, port: int) -> str:
        """Generate init.sh for Python project."""
        has_pyproject = (project_path / "pyproject.toml").exists()
        has_requirements = (project_path / "requirements.txt").exists()
        has_main = (project_path / "main.py").exists()
        has_app = (project_path / "app.py").exists()
        has_manage_py = (project_path / "manage.py").exists()  # Django

        install_cmd = ""
        if has_pyproject:
            install_cmd = "pip install -e ."
        elif has_requirements:
            install_cmd = "pip install -r requirements.txt"

        # Detect framework
        start_cmd = "python main.py" if has_main else "python app.py"
        if has_manage_py:
            start_cmd = f"python manage.py runserver 0.0.0.0:{port}"

        # Check for FastAPI/Uvicorn
        requirements_file = project_path / "requirements.txt"
        if requirements_file.exists():
            try:
                content = requirements_file.read_text()
                if "fastapi" in content.lower() or "uvicorn" in content.lower():
                    if has_main:
                        start_cmd = f"uvicorn main:app --host 0.0.0.0 --port {port}"
                    elif has_app:
                        start_cmd = f"uvicorn app:app --host 0.0.0.0 --port {port}"
            except Exception:
                pass

        return f"""#!/bin/bash
# AutoDev Init Script for Python
# Generated automatically by AutoDev

set -e

echo "========================================="
echo "AutoDev - Starting Python Development"
echo "========================================="
echo ""

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
{install_cmd}

# Start application
echo ""
echo "Starting development server on port {port}..."
{start_cmd}

"""

    @staticmethod
    def _generate_rust(project_path: Path, port: int) -> str:
        """Generate init.sh for Rust project."""
        return f"""#!/bin/bash
# AutoDev Init Script for Rust
# Generated automatically by AutoDev

set -e

echo "========================================="
echo "AutoDev - Starting Rust Development"
echo "========================================="
echo ""

# Build the project
echo "Building project..."
cargo build

# Run the application
echo ""
echo "Starting development server..."
cargo run

"""

    @staticmethod
    def _generate_go(project_path: Path, port: int) -> str:
        """Generate init.sh for Go project."""
        return f"""#!/bin/bash
# AutoDev Init Script for Go
# Generated automatically by AutoDev

set -e

echo "========================================="
echo "AutoDev - Starting Go Development"
echo "========================================="
echo ""

# Download dependencies
echo "Downloading dependencies..."
go mod download

# Run the application
echo ""
echo "Starting development server on port {port}..."
go run main.go

"""

    @staticmethod
    def _generate_java_maven(project_path: Path, port: int) -> str:
        """Generate init.sh for Java Maven project."""
        return f"""#!/bin/bash
# AutoDev Init Script for Java (Maven)
# Generated automatically by AutoDev

set -e

echo "========================================="
echo "AutoDev - Starting Java Development"
echo "========================================="
echo ""

# Build the project
echo "Building project..."
mvn clean install -DskipTests

# Run Spring Boot if detected
if grep -q "spring-boot" pom.xml; then
    echo ""
    echo "Starting Spring Boot application on port {port}..."
    mvn spring-boot:run -Dspring-boot.run.arguments=--server.port={port}
else
    echo ""
    echo "Running application..."
    mvn exec:java
fi

"""

    @staticmethod
    def _generate_java_gradle(project_path: Path, port: int) -> str:
        """Generate init.sh for Java Gradle project."""
        return f"""#!/bin/bash
# AutoDev Init Script for Java (Gradle)
# Generated automatically by AutoDev

set -e

echo "========================================="
echo "AutoDev - Starting Java Development"
echo "========================================="
echo ""

# Make gradlew executable if needed
if [ -f "gradlew" ]; then
    chmod +x gradlew
    GRADLE_CMD="./gradlew"
else
    GRADLE_CMD="gradle"
fi

# Build the project
echo "Building project..."
$GRADLE_CMD build -x test

# Run Spring Boot if detected
if grep -q "spring-boot" build.gradle*; then
    echo ""
    echo "Starting Spring Boot application on port {port}..."
    $GRADLE_CMD bootRun --args='--server.port={port}'
else
    echo ""
    echo "Running application..."
    $GRADLE_CMD run
fi

"""

    @staticmethod
    def _generate_ruby(project_path: Path, port: int) -> str:
        """Generate init.sh for Ruby project."""
        return f"""#!/bin/bash
# AutoDev Init Script for Ruby
# Generated automatically by AutoDev

set -e

echo "========================================="
echo "AutoDev - Starting Ruby Development"
echo "========================================="
echo ""

# Install dependencies
if [ -f "Gemfile" ]; then
    echo "Installing dependencies..."
    bundle install
fi

# Start Rails server if detected
if [ -f "bin/rails" ]; then
    echo ""
    echo "Starting Rails server on port {port}..."
    bin/rails server -p {port}
elif [ -f "config.ru" ]; then
    echo ""
    echo "Starting Rack server on port {port}..."
    rackup -p {port}
else
    echo ""
    echo "Starting Ruby application..."
    ruby app.rb
fi

"""

    @staticmethod
    def _generate_php(project_path: Path, port: int) -> str:
        """Generate init.sh for PHP project."""
        return f"""#!/bin/bash
# AutoDev Init Script for PHP
# Generated automatically by AutoDev

set -e

echo "========================================="
echo "AutoDev - Starting PHP Development"
echo "========================================="
echo ""

# Install dependencies
if [ -f "composer.json" ]; then
    echo "Installing dependencies..."
    composer install
fi

# Start Laravel if detected
if [ -f "artisan" ]; then
    echo ""
    echo "Starting Laravel development server on port {port}..."
    php artisan serve --port={port}
else
    echo ""
    echo "Starting PHP development server on port {port}..."
    php -S localhost:{port}
fi

"""

    @staticmethod
    def _generate_generic(project_path: Path, port: int) -> str:
        """Generate generic init.sh."""
        return f"""#!/bin/bash
# AutoDev Init Script (Generic)
# Generated automatically by AutoDev

set -e

echo "========================================="
echo "AutoDev - Starting Development Server"
echo "========================================="
echo ""

# Add project-specific setup commands here
# Examples:
# pip install -r requirements.txt
# npm install
# cargo build

echo "Project setup complete."
echo ""
echo "Please configure this init.sh script for your specific project."
echo "Starting a simple HTTP server on port {port}..."
python3 -m http.server {port}

"""


def create_init_script(
    project_path: Path,
    project_type: Optional[str] = None,
    port: int = 3000,
    make_executable: bool = True,
) -> Path:
    """
    Create an init.sh script in the project directory.

    Args:
        project_path: Path to the project.
        project_type: Optional project type override.
        port: Port for dev server.
        make_executable: Whether to make the script executable.

    Returns:
        Path to the created init.sh file.
    """
    project_path = Path(project_path)
    init_script_path = project_path / "init.sh"

    # Generate script content
    content = InitScriptGenerator.generate(project_path, project_type, port)

    # Write the script
    init_script_path.write_text(content)

    # Make executable
    if make_executable:
        import os
        import stat
        current_mode = init_script_path.stat().st_mode
        init_script_path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    logger.info(f"Created init.sh at {init_script_path}")
    return init_script_path

# Fintegrate Commit, Tag & Push Script
# Interactive script for committing changes, managing semantic versioning, tagging and pushing to `main`.

function Show-Menu {
    Clear-Host
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  Fintegrate Commit -> Tag -> Push" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""

    # Check current version
    $versionFile = "VERSION"
    if (Test-Path $versionFile) {
        $currentVersion = Get-Content $versionFile -Raw
        $currentVersion = $currentVersion.Trim()
        Write-Host "Current Version: " -NoNewline -ForegroundColor Yellow
        Write-Host "$currentVersion" -ForegroundColor Green
    } else {
        Write-Host "Current Version: " -NoNewline -ForegroundColor Yellow
        Write-Host "Not set (VERSION file missing)" -ForegroundColor Red
    }

    # Check Git status
    $gitStatus = git status --porcelain 2>&1
    if ($LASTEXITCODE -eq 0 -and $gitStatus) {
        Write-Host "Git Status:     " -NoNewline -ForegroundColor Yellow
        Write-Host "Uncommitted changes" -ForegroundColor Red
    } elseif ($LASTEXITCODE -eq 0) {
        Write-Host "Git Status:     " -NoNewline -ForegroundColor Yellow
        Write-Host "Clean" -ForegroundColor Green
    } else {
        Write-Host "Git Status:     " -NoNewline -ForegroundColor Yellow
        Write-Host "Not a Git repository" -ForegroundColor Red
    }

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "[1] Main Flow: Commit -> Tag -> Push (main)" -ForegroundColor Magenta
    Write-Host "    Commit all changes, update version/tag, push main and tags" -ForegroundColor Gray
    Write-Host ""
    Write-Host "[2] Show Current Tags" -ForegroundColor Green
    Write-Host "    Display local and remote Git tags" -ForegroundColor Gray
    Write-Host ""
    Write-Host "[3] Create New Tag (Patch)" -ForegroundColor Yellow
    Write-Host "    Increment patch version (1.0.0 -> 1.0.1)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "[4] Create New Tag (Minor)" -ForegroundColor Yellow
    Write-Host "    Increment minor version (1.0.0 -> 1.1.0)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "[5] Create New Tag (Major)" -ForegroundColor Yellow
    Write-Host "    Increment major version (1.0.0 -> 2.0.0)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "[6] Create Custom Tag" -ForegroundColor Magenta
    Write-Host "    Set specific version number" -ForegroundColor Gray
    Write-Host ""
    Write-Host "[7] Push Tags to Remote" -ForegroundColor Cyan
    Write-Host "    Push all local tags to GitHub" -ForegroundColor Gray
    Write-Host ""
    Write-Host "[8] Update CHANGELOG.md" -ForegroundColor White
    Write-Host "    Add new version section to changelog" -ForegroundColor Gray
    Write-Host ""
    Write-Host "[9] Show Version History" -ForegroundColor White
    Write-Host "    Display recent commits and tags" -ForegroundColor Gray
    Write-Host ""
    Write-Host "[10] Setup Git Hooks" -ForegroundColor Gray
    Write-Host "    Configure reminders for version updates" -ForegroundColor Gray
    Write-Host ""
    Write-Host "[Q] Quit" -ForegroundColor White
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
}

function Get-CurrentVersion {
    $versionFile = "VERSION"
    if (Test-Path $versionFile) {
        $version = Get-Content $versionFile -Raw
        return $version.Trim()
    }
    return $null
}

function Set-Version {
    param([string]$newVersion)

    $versionFile = "VERSION"
    $newVersion | Out-File $versionFile -Force -Encoding UTF8
    Write-Host "Updated VERSION file to: $newVersion" -ForegroundColor Green
}

function Increment-Version {
    param([string]$type)  # "patch", "minor", "major"

    $currentVersion = Get-CurrentVersion
    if (-not $currentVersion) {
        Write-Host "ERROR: No current version found. Create VERSION file first." -ForegroundColor Red
        return $null
    }

    # Parse semantic version (major.minor.patch)
    $versionParts = $currentVersion -split '\.'
    if ($versionParts.Length -ne 3) {
        Write-Host "ERROR: Invalid version format. Expected: major.minor.patch" -ForegroundColor Red
        return $null
    }

    $major = [int]$versionParts[0]
    $minor = [int]$versionParts[1]
    $patch = [int]$versionParts[2]

    switch ($type) {
        "patch" { $patch++ }
        "minor" { $minor++; $patch = 0 }
        "major" { $major++; $minor = 0; $patch = 0 }
    }

    $newVersion = "$major.$minor.$patch"
    return $newVersion
}

function Create-Tag {
    param([string]$version)

    Write-Host "Creating tag: v$version" -ForegroundColor Yellow

    # Create annotated tag
    $tagMessage = "Release version $version"
    $result = git tag -a "v$version" -m "$tagMessage" 2>&1

    if ($LASTEXITCODE -eq 0) {
        Write-Host "OK: Tag v$version created successfully" -ForegroundColor Green
        return $true
    } else {
        Write-Host "ERROR: Failed to create tag: $result" -ForegroundColor Red
        return $false
    }
}

function Push-Tags {
    Write-Host "Pushing tags to remote..." -ForegroundColor Yellow

    $result = git push origin --tags 2>&1

    if ($LASTEXITCODE -eq 0) {
        Write-Host "OK: All tags pushed to remote" -ForegroundColor Green
        return $true
    } else {
        Write-Host "ERROR: Failed to push tags: $result" -ForegroundColor Red
        return $false
    }
}

function Build-And-Tag-Images {
    param([string]$version)

    # Default image build map: repo -> Dockerfile (relative to repo root's docker/)
    $buildMap = @{
        'fintegrate-customer_service' = 'Dockerfile.customer_service'
        'fintegrate-aml_service' = 'Dockerfile.aml_service'
        'fintegrate-event_consumer' = 'Dockerfile.event_consumer'
    }

    Write-Host "Image version to use: $version" -ForegroundColor Cyan
    $choice = Read-Host "Choose: [b]uild images, [r]etag existing :latest, [s]kip" -Default 's'

    if ($choice -eq 's' -or $choice -eq 'S') {
        Write-Host "Skipping image build/tag step" -ForegroundColor Gray
        return
    }

    # Change into docker directory if it exists
    $dockerDir = Join-Path (Get-Location) 'docker'
    if (Test-Path $dockerDir) { Push-Location $dockerDir }

    foreach ($repo in $buildMap.Keys) {
        $dockerfile = $buildMap[$repo]
        if ($choice -eq 'b' -or $choice -eq 'B') {
            Write-Host "Building $repo using $dockerfile..." -ForegroundColor Yellow
            $cmd = "docker build -f $dockerfile -t $($repo):$($version) -t $($repo):latest ."
            Write-Host $cmd -ForegroundColor DarkGray
            iex $cmd
            if ($LASTEXITCODE -ne 0) {
                Write-Host "ERROR: Build failed for $repo" -ForegroundColor Red
            } else {
                Write-Host "OK: Built $($repo):$($version)" -ForegroundColor Green
            }
        } else {
            # retag latest -> version
            Write-Host "Retagging $($repo):latest -> $($repo):$($version)" -ForegroundColor Yellow
            $tagCmd = "docker tag $($repo):latest $($repo):$($version)"
            iex $tagCmd
            if ($LASTEXITCODE -ne 0) {
                Write-Host "ERROR: Retag failed for $repo (ensure $repo:latest exists)" -ForegroundColor Red
            } else {
                Write-Host "OK: Tagged $($repo):$($version)" -ForegroundColor Green
            }
        }
    }

    if (Test-Path $dockerDir) { Pop-Location }

    # Optionally push images to a registry
    $pushNow = Read-Host "Push built/tagged images to a registry now? (y/N)"
    if ($pushNow -eq 'y' -or $pushNow -eq 'Y') {
        $registry = Read-Host "Registry prefix (e.g. myregistry.com/myorg) or leave empty for Docker Hub/localhost"
        foreach ($repo in $buildMap.Keys) {
            $src = "$($repo):$($version)"
            if ($registry) {
                $dst = "$registry/$($repo):$($version)"
                Write-Host "Tagging $src -> $dst" -ForegroundColor Yellow
                iex "docker tag $src $dst"
                Write-Host "Pushing $dst..." -ForegroundColor Yellow
                iex "docker push $dst"
            } else {
                Write-Host "Pushing $src to default registry..." -ForegroundColor Yellow
                iex "docker push $src"
            }
            if ($LASTEXITCODE -ne 0) {
                Write-Host "ERROR: Failed to push image for $repo" -ForegroundColor Red
            } else {
                Write-Host "OK: Pushed image for $repo" -ForegroundColor Green
            }
        }
    }
}

function Update-Changelog {
    param([string]$version)

    $changelogFile = "CHANGELOG.md"

    if (-not (Test-Path $changelogFile)) {
        Write-Host "Creating new CHANGELOG.md file..." -ForegroundColor Yellow
        $initialContent = @'
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial project setup

### Changed
-

### Fixed
-

### Removed
-

### Security
-
'@
        $initialContent | Out-File $changelogFile -Force -Encoding UTF8
        Write-Host "OK: CHANGELOG.md created" -ForegroundColor Green
        return
    }

    # Read current changelog
    $content = Get-Content $changelogFile -Raw

    # Check if version already exists
    if ($content -match "## \[$version\]") {
        Write-Host "Version $version already exists in CHANGELOG.md" -ForegroundColor Yellow
        return
    }

    # Get today's date
    $today = Get-Date -Format "yyyy-MM-dd"

    # Create new version section
    $newSection = @'

## [$version] - $today

### Added
-

### Changed
-

### Fixed
-

### Removed
-

### Security
-

'@

    # Insert after [Unreleased] section
    $pattern = "## \[Unreleased\]"
    if ($content -match $pattern) {
        $content = $content -replace $pattern, "## [Unreleased]`n$newSection`n## [Unreleased]"
    } else {
        # If no [Unreleased] section, append to top
        $content = $newSection + "`n" + $content
    }

    $content | Out-File $changelogFile -Force -Encoding UTF8
    Write-Host "OK: Added version $version section to CHANGELOG.md" -ForegroundColor Green
    Write-Host "  Edit the changelog to document your changes" -ForegroundColor Cyan
}

function Setup-GitHooks {
    Write-Host "Setting up Git hooks for version reminders..." -ForegroundColor Yellow

    $hooksDir = ".git\hooks"
    if (-not (Test-Path $hooksDir)) {
        Write-Host "ERROR: Not a Git repository" -ForegroundColor Red
        return
    }

    # Create pre-commit hook
    $preCommitHook = @'
#!/bin/bash
# Pre-commit hook to remind about version updates

echo "Checking for version updates..."

# Check if VERSION file exists
if [ ! -f "VERSION" ]; then
    echo "VERSION file not found. Run commit-and-push.ps1 to create it."
    exit 1
fi

# Check if CHANGELOG.md exists and has unreleased section
if [ ! -f "CHANGELOG.md" ] || ! grep -q "## \[Unreleased\]" CHANGELOG.md; then
    echo "CHANGELOG.md missing or no [Unreleased] section. Run commit-and-push.ps1 to update it."
fi

echo "Pre-commit checks passed"
'@

    $preCommitHook | Out-File "$hooksDir\pre-commit" -Force -Encoding UTF8

    # Create pre-push hook
    $prePushHook = @'
#!/bin/bash
# Pre-push hook to remind about tagging

echo "Checking for new tags before push..."

# Get latest commit
LATEST_COMMIT=`git rev-parse HEAD`

# Check if latest commit has a tag
TAG_COUNT=`git tag --points-at $LATEST_COMMIT | wc -l`

if [ "$TAG_COUNT" -eq "0" ]; then
    echo "Latest commit has no tag. Consider creating a version tag."
    echo "   Run: .\commit-and-push.ps1"
    echo ""
    echo "   Press Enter to continue push, or Ctrl+C to cancel"
    read -p ""
fi

echo "Pre-push checks passed"
'@

    $prePushHook | Out-File "$hooksDir\pre-push" -Force -Encoding UTF8

    # Make hooks executable (on Windows, this might not be necessary)
    try {
        chmod +x "$hooksDir\pre-commit" 2>$null
        chmod +x "$hooksDir\pre-push" 2>$null
    } catch {
        # Ignore on Windows
    }

    Write-Host "OK: Git hooks configured" -ForegroundColor Green
    Write-Host "  Pre-commit: Reminds about VERSION and CHANGELOG" -ForegroundColor Gray
    Write-Host "  Pre-push: Reminds about tagging commits" -ForegroundColor Gray
}

function Main-Commit-Tag-Push {
    # Ensure inside a git repo
    git rev-parse --is-inside-work-tree 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Not a Git repository" -ForegroundColor Red
        return
    }

    Write-Host "Staging all changes..." -ForegroundColor Yellow
    git add -A 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to stage changes" -ForegroundColor Red
        return
    }

    $commitMsg = Read-Host "Enter commit message (single line)"
    if (-not $commitMsg) {
        Write-Host "No commit message provided. Aborting commit." -ForegroundColor Red
    } else {
        git commit -m "$commitMsg" 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "git commit failed (there may be nothing to commit)" -ForegroundColor Yellow
        } else {
            Write-Host "OK: Commit created" -ForegroundColor Green
        }
    }

    # Ask to update version and create tag
    $doTag = Read-Host "Update version and create tag now? (y/N)"
    if ($doTag -eq 'y' -or $doTag -eq 'Y') {
        Write-Host "Select version bump type: [p]atch / [m]inor / [M]ajor / [c]ustom" -ForegroundColor Cyan
        $vt = Read-Host "Type"
        switch ($vt) {
            'p' { $newVersion = Increment-Version 'patch' }
            'm' { $newVersion = Increment-Version 'minor' }
            'M' { $newVersion = Increment-Version 'major' }
            'c' {
                $v = Read-Host "Enter custom version (major.minor.patch)"
                if (-not $v -or $v -notmatch '^\d+\.\d+\.\d+$') {
                    Write-Host "Invalid version format" -ForegroundColor Red
                    $newVersion = $null
                } else {
                    $newVersion = $v
                }
            }
            default { Write-Host "Unknown option" -ForegroundColor Red; $newVersion = $null }
        }

        if ($newVersion) {
            Set-Version $newVersion
            Update-Changelog $newVersion

            # Offer to build/retag images with the new version
            $doImages = Read-Host "Build or retag Docker images for version $newVersion now? (y/N)"
            if ($doImages -eq 'y' -or $doImages -eq 'Y') {
                Build-And-Tag-Images $newVersion
            }

            if (Create-Tag $newVersion) {
                $pushTagsNow = Read-Host "Push tags to remote now? (y/N)"
                if ($pushTagsNow -eq 'y' -or $pushTagsNow -eq 'Y') { Push-Tags }
            }
        }
    }

    # Push main branch
    $pushMain = Read-Host "Push branch 'main' to origin now? (y/N)"
    if ($pushMain -eq 'y' -or $pushMain -eq 'Y') {
        Write-Host "Pushing main to origin..." -ForegroundColor Yellow
        git push origin main 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "OK: main pushed to origin" -ForegroundColor Green
        } else {
            Write-Host "ERROR: Failed to push main" -ForegroundColor Red
        }
    }
}

# Main loop
while ($true) {
    Show-Menu
    $choice = Read-Host "Select option"

    switch ($choice) {
        "1" { Main-Commit-Tag-Push; Read-Host "`nPress Enter to continue" }

        "2" {
            Write-Host "`n[Current Tags]" -ForegroundColor Cyan
            Write-Host ""

            Write-Host "Local tags:" -ForegroundColor Yellow
            git tag -l 2>$null
            if ($LASTEXITCODE -ne 0) {
                Write-Host "  Not a Git repository" -ForegroundColor Red
            }

            Write-Host ""
            Write-Host "Remote tags:" -ForegroundColor Yellow
            git ls-remote --tags origin 2>$null | ForEach-Object {
                $parts = $_ -split '\s+'
                $tag = $parts[1] -replace 'refs/tags/', ''
                "  $tag"
            }
            if ($LASTEXITCODE -ne 0) {
                Write-Host "  No remote repository or network error" -ForegroundColor Red
            }

            Read-Host "`nPress Enter to continue"
        }

        "3" {
            Write-Host "`n[Create Patch Version Tag]" -ForegroundColor Yellow

            $newVersion = Increment-Version "patch"
            if (-not $newVersion) { Read-Host "`nPress Enter to continue"; continue }

            Write-Host "New version will be: $newVersion" -ForegroundColor Cyan
            $confirm = Read-Host "Continue? (y/N)"
            if ($confirm -ne "y" -and $confirm -ne "Y") {
                Write-Host "Cancelled" -ForegroundColor Gray
                Read-Host "`nPress Enter to continue"
                continue
            }

            Set-Version $newVersion
            Update-Changelog $newVersion

            if (Create-Tag $newVersion) {
                Write-Host ""
                $pushConfirm = Read-Host "Push tag to remote now? (y/N)"
                if ($pushConfirm -eq "y" -or $pushConfirm -eq "Y") {
                    Push-Tags
                }
            }

            Read-Host "`nPress Enter to continue"
        }

        "4" {
            Write-Host "`n[Create Minor Version Tag]" -ForegroundColor Yellow

            $newVersion = Increment-Version "minor"
            if (-not $newVersion) { Read-Host "`nPress Enter to continue"; continue }

            Write-Host "New version will be: $newVersion" -ForegroundColor Cyan
            $confirm = Read-Host "Continue? (y/N)"
            if ($confirm -ne "y" -and $confirm -ne "Y") {
                Write-Host "Cancelled" -ForegroundColor Gray
                Read-Host "`nPress Enter to continue"
                continue
            }

            Set-Version $newVersion
            Update-Changelog $newVersion

            if (Create-Tag $newVersion) {
                Write-Host ""
                $pushConfirm = Read-Host "Push tag to remote now? (y/N)"
                if ($pushConfirm -eq "y" -or $pushConfirm -eq "Y") {
                    Push-Tags
                }
            }

            Read-Host "`nPress Enter to continue"
        }

        "5" {
            Write-Host "`n[Create Major Version Tag]" -ForegroundColor Yellow

            $newVersion = Increment-Version "major"
            if (-not $newVersion) { Read-Host "`nPress Enter to continue"; continue }

            Write-Host "New version will be: $newVersion" -ForegroundColor Cyan
            $confirm = Read-Host "Continue? (y/N)"
            if ($confirm -ne "y" -and $confirm -ne "Y") {
                Write-Host "Cancelled" -ForegroundColor Gray
                Read-Host "`nPress Enter to continue"
                continue
            }

            Set-Version $newVersion
            Update-Changelog $newVersion

            if (Create-Tag $newVersion) {
                Write-Host ""
                $pushConfirm = Read-Host "Push tag to remote now? (y/N)"
                if ($pushConfirm -eq "y" -or $pushConfirm -eq "Y") {
                    Push-Tags
                }
            }

            Read-Host "`nPress Enter to continue"
        }

        "6" {
            Write-Host "`n[Create Custom Tag]" -ForegroundColor Magenta

            $currentVersion = Get-CurrentVersion
            if ($currentVersion) {
                Write-Host "Current version: $currentVersion" -ForegroundColor Gray
            }

            $newVersion = Read-Host "Enter new version (e.g., 1.2.3)"
            if (-not $newVersion -or $newVersion -notmatch '^\d+\.\d+\.\d+$') {
                Write-Host "Invalid version format. Use: major.minor.patch" -ForegroundColor Red
                Read-Host "`nPress Enter to continue"
                continue
            }

            Write-Host "New version will be: $newVersion" -ForegroundColor Cyan
            $confirm = Read-Host "Continue? (y/N)"
            if ($confirm -ne "y" -and $confirm -ne "Y") {
                Write-Host "Cancelled" -ForegroundColor Gray
                Read-Host "`nPress Enter to continue"
                continue
            }

            Set-Version $newVersion
            Update-Changelog $newVersion

            if (Create-Tag $newVersion) {
                Write-Host ""
                $pushConfirm = Read-Host "Push tag to remote now? (y/N)"
                if ($pushConfirm -eq "y" -or $pushConfirm -eq "Y") {
                    Push-Tags
                }
            }

            Read-Host "`nPress Enter to continue"
        }

        "7" {
            Write-Host "`n[Pushing Tags to Remote]" -ForegroundColor Cyan
            Push-Tags
            Read-Host "`nPress Enter to continue"
        }

        "8" {
            Write-Host "`n[Update CHANGELOG.md]" -ForegroundColor White

            $currentVersion = Get-CurrentVersion
            if (-not $currentVersion) {
                Write-Host "ERROR: No VERSION file found" -ForegroundColor Red
                Read-Host "`nPress Enter to continue"
                continue
            }

            Update-Changelog $currentVersion
            Read-Host "`nPress Enter to continue"
        }

        "9" {
            Write-Host "`n[Version History]" -ForegroundColor White
            Write-Host ""

            Write-Host "Recent commits with tags:" -ForegroundColor Yellow
            git log --oneline --decorate --tags -10 2>$null
            if ($LASTEXITCODE -ne 0) {
                Write-Host "  Not a Git repository" -ForegroundColor Red
            }

            Write-Host ""
            Write-Host "Tag details:" -ForegroundColor Yellow
            git tag -l -n 2>$null
            if ($LASTEXITCODE -ne 0) {
                Write-Host "  No tags found" -ForegroundColor Red
            }

            Read-Host "`nPress Enter to continue"
        }

        "10" {
            Write-Host "`n[Setup Git Hooks]" -ForegroundColor Gray
            Setup-GitHooks
            Read-Host "`nPress Enter to continue"
        }

        "q" {
            Write-Host "`nGoodbye!" -ForegroundColor Cyan
            exit
        }

        "Q" {
            Write-Host "`nGoodbye!" -ForegroundColor Cyan
            exit
        }

        default {
            Write-Host "`nInvalid option" -ForegroundColor Red
            Start-Sleep -Seconds 1
        }
    }
}

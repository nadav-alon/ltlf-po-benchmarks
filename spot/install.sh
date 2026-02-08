#!/bin/bash

# Ensure we are in the spot directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

# Improved: Use version sort and pick the latest tarball
SPOT_TAR=$(ls -v spot-*.tar.gz 2>/dev/null | tail -n 1)
if [ -z "$SPOT_TAR" ]; then
    echo "Error: No Spot tarball found in $SCRIPT_DIR"
    exit 1
fi

EXTRACT_DIR="${SPOT_TAR%.tar.gz}"
echo "Detected latest version: $SPOT_TAR"

# Improved: Clean up any previous extraction directory to ensure a clean build
if [ -d "$EXTRACT_DIR" ]; then
    echo "Removing existing extraction directory: $EXTRACT_DIR"
    rm -rf "$EXTRACT_DIR"
fi

echo "Extracting $SPOT_TAR..."
tar --extract --file="$SPOT_TAR" --gzip

# Define a local installation directory (absolute path)
PREFIX="$SCRIPT_DIR/local"
mkdir -p "$PREFIX"

echo "Configuring and building Spot..."
cd "$EXTRACT_DIR" || exit 1
./configure --prefix="$PREFIX" --disable-devel
make -j$(nproc)
make install

cd ..

# Improved: Clean up the source files after successful installation to save space
echo "Cleaning up extraction directory..."
rm -rf "$EXTRACT_DIR"

echo "=========================================================="
echo "Spot updated/installed locally to: $PREFIX"
echo "To use it, add the following to your environment:"
echo "export PATH=\"$PREFIX/bin:\$PATH\""
echo "export LD_LIBRARY_PATH=\"$PREFIX/lib:\$LD_LIBRARY_PATH\""
echo "=========================================================="

#!/bin/bash

# Ensure we are in the spot directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

SPOT_TAR=$(ls spot-*.tar.gz | head -n 1)
if [ -z "$SPOT_TAR" ]; then
    echo "Error: Spot tarball not found."
    exit 1
fi

EXTRACT_DIR="${SPOT_TAR%.tar.gz}"
tar --extract --file="$SPOT_TAR" --gzip --verbose

# Define a local installation directory (absolute path)
PREFIX="$SCRIPT_DIR/local"
mkdir -p "$PREFIX"

cd "$EXTRACT_DIR" || exit 1
./configure --prefix="$PREFIX" --disable-devel
make -j$(nproc)
make install

cd ..
echo "=========================================================="
echo "Spot installed locally to: $PREFIX"
echo "To use it, add the following to your environment:"
echo "export PATH=\"$PREFIX/bin:\$PATH\""
echo "export LD_LIBRARY_PATH=\"$PREFIX/lib:\$LD_LIBRARY_PATH\""
echo "=========================================================="

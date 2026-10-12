# XeStrata (MistVVK/XeStrata, LGPL-3.0) for Qwen3.8-Flash-Next on an Intel Arc Pro B70.
# The release's Ubuntu 26.04 package (the contrib-llvm build, which hands dense matrix products to oneMKL), Intel's GPU
# runtime from the Ubuntu archive (Level Zero and OpenCL 26.05.37020.3) and oneMKL 2026.1 from Intel's repository.
# The package is downloaded from the GitHub release and checked against its SHA-256.
FROM ubuntu:26.04@sha256:f144425ff09be612d6d9ad965196e9cdc23dae1f42110a8a11a3e9a8198759f7
ARG DEBIAN_FRONTEND=noninteractive
ARG XESTRATA_TAG=xe0.1.40.2.2
ARG XESTRATA_DEB=xestrata-contrib-cuda13.1_0.1.40.2-3_amd64.deb
ARG XESTRATA_SHA256=6ee57e5f5fa79c2eec9a9b0f829fd1eec403de700f03cf88486284ace4c07802
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl gpg \
 && curl -fsSL -o /tmp/$XESTRATA_DEB https://github.com/MistVVK/XeStrata/releases/download/$XESTRATA_TAG/$XESTRATA_DEB \
 && echo "$XESTRATA_SHA256  /tmp/$XESTRATA_DEB" | sha256sum -c - \
 && curl -fsSL https://apt.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB | gpg --dearmor -o /usr/share/keyrings/oneapi.gpg \
 && echo "deb [signed-by=/usr/share/keyrings/oneapi.gpg] https://apt.repos.intel.com/oneapi all main" > /etc/apt/sources.list.d/oneapi.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends /tmp/$XESTRATA_DEB libze1 libze-intel-gpu1 libigc2 libigdfcl2 \
      mesa-vulkan-drivers intel-oneapi-mkl-sycl-blas-2026.1 procps \
 && rm -rf /var/lib/apt/lists/* /tmp/*.deb
# Recoverable GPU page faults off. In the compute runtime's default mode, xe backs the engine's host buffers up to
# swap under memory pressure, and the engine faults when it next polls them. With these keys it did not, so swap can
# stay on. See docs/settings.md.
ENV NEOReadDebugKeys=1 EnableRecoverablePageFaults=0 HOME=/x/home
COPY entrypoint.sh /opt/recipe/entrypoint.sh
ENTRYPOINT ["/opt/recipe/entrypoint.sh"]

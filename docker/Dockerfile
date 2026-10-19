# XeStrata (MistVVK/XeStrata, LGPL-3.0) for Qwen3.8-Flash-Next on an Intel Arc Pro B70.
# The release's Ubuntu 26.04 package (the contrib-llvm build, which hands dense matrix products to oneMKL), Intel's GPU
# runtime from the Ubuntu archive and the oneMKL release the package was built against, from Intel's repository.
# The package is downloaded from the GitHub release and checked against its SHA-256.
FROM ubuntu:26.04@sha256:f144425ff09be612d6d9ad965196e9cdc23dae1f42110a8a11a3e9a8198759f7
ARG DEBIAN_FRONTEND=noninteractive
ARG XESTRATA_TAG=xe0.1.45-1
ARG XESTRATA_DEB=xestrata-contrib-cuda13.1_0.1.45-1_amd64.deb
ARG XESTRATA_SHA256=88c9c0b0891897b4ffd70a922598b18d987f07e289f6e13f076229c851db8ddf
# the oneMKL release the package was built against (runtime.onemkl in its BUILD.json)
ARG ONEMKL=2026.2
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl gpg \
 && curl -fsSL -o /tmp/$XESTRATA_DEB https://github.com/MistVVK/XeStrata/releases/download/$XESTRATA_TAG/$XESTRATA_DEB \
 && echo "$XESTRATA_SHA256  /tmp/$XESTRATA_DEB" | sha256sum -c - \
 && curl -fsSL https://apt.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB | gpg --dearmor -o /usr/share/keyrings/oneapi.gpg \
 && echo "deb [signed-by=/usr/share/keyrings/oneapi.gpg] https://apt.repos.intel.com/oneapi all main" > /etc/apt/sources.list.d/oneapi.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends /tmp/$XESTRATA_DEB libze1 libze-intel-gpu1 libigc2 libigdfcl2 \
      mesa-vulkan-drivers intel-oneapi-mkl-sycl-blas-$ONEMKL procps \
 && rm -rf /var/lib/apt/lists/* /tmp/*.deb
# The launcher reads the package's version "0.1.45-1" as 0.1 (the "45-1" part is not a digit), takes the engine for
# one older than 0.1.13 and rewrites --prefill auto to 2048-token chunks at every start, which more than doubles the
# time to read a long prompt. Split the version on "-" as well; the grep fails the build if the line has changed.
RUN sed -i 's/for x in v.split("\.")\[:3\] if x.isdigit())/for x in re.split(r"[.-]", v)[:3] if x.isdigit())/' /usr/share/xestrata/setup.py \
 && grep -q 're.split(r"\[.-\]", v)\[:3\]' /usr/share/xestrata/setup.py
# Recoverable GPU page faults off. In the compute runtime's default mode, xe backs the engine's host buffers up to
# swap under memory pressure, and the engine faults when it next polls them. With these keys it did not, so swap can
# stay on. See docs/settings.md.
# XESTRATA_UPDATE_CHECK=0: the server would ask GitHub for a newer release at start and every six hours; the release
# is pinned above instead.
ENV NEOReadDebugKeys=1 EnableRecoverablePageFaults=0 HOME=/x/home XESTRATA_MKL_LIB=/opt/intel/oneapi/mkl/$ONEMKL/lib \
    XESTRATA_UPDATE_CHECK=0
COPY entrypoint.sh /opt/recipe/entrypoint.sh
ENTRYPOINT ["/opt/recipe/entrypoint.sh"]

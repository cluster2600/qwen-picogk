# AdditiveFOAM 2.0.0 on OpenFOAM-14 for Phase 2 of docs/PHYSICS_EVIDENCE_PLAN.md.
# Built locally and run offline as a separate tool. OpenFOAM and AdditiveFOAM
# are GPL-3.0; their sources are fetched at build time and never copied into
# this repository. Do not publish the built image without offering the sources.
ARG UBUNTU_BASE_IMAGE=ubuntu:24.04@sha256:33ceb71981b602c1a7443a53469e4dba065f7503eab3078a2d7a57a2ab987517
FROM ${UBUNTU_BASE_IMAGE}

# Release 2.0.0 (2026-08-31) and the OpenFOAM Foundation apt key, by hash.
ARG ADDITIVEFOAM_COMMIT=9c05c5eb54db03faa342b14b0806efe740de8c44
ARG OPENFOAM_KEY_SHA256=fbaacfe37e704494f6e65ab424e67b031191769e84c31185acb701f9e74fe0a9

# OpenFOAM puts user-built binaries under $HOME/OpenFOAM/$USER-14. Fixing both
# lets the solver run later under any host uid with a read-only image.
ENV DEBIAN_FRONTEND=noninteractive HOME=/opt/foam USER=foam

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git \
 && curl -fsSL https://dl.openfoam.org/gpg.key -o /usr/share/keyrings/openfoam.asc \
 && echo "${OPENFOAM_KEY_SHA256}  /usr/share/keyrings/openfoam.asc" | sha256sum -c - \
 && echo "deb [signed-by=/usr/share/keyrings/openfoam.asc] http://dl.openfoam.org/ubuntu noble main" \
      > /etc/apt/sources.list.d/openfoam.list \
 && apt-get update \
 && apt-get install -y openfoam14 \
 && rm -rf /var/lib/apt/lists/*

RUN git clone --filter=blob:none https://github.com/ORNL/AdditiveFOAM /opt/AdditiveFOAM \
 && git -C /opt/AdditiveFOAM checkout --detach "${ADDITIVEFOAM_COMMIT}" \
 && test "$(git -C /opt/AdditiveFOAM rev-parse HEAD)" = "${ADDITIVEFOAM_COMMIT}"

RUN mkdir -p /opt/foam \
 && bash -c '. /opt/openfoam14/etc/bashrc && cd /opt/AdditiveFOAM && . ./etc/bashrc \
      && ./Allwmake -j 8 > /opt/foam/build.log 2>&1 || { tail -60 /opt/foam/build.log; exit 1; }' \
 && bash -c '. /opt/openfoam14/etc/bashrc && . /opt/AdditiveFOAM/etc/bashrc && command -v additiveFoam' \
 && dpkg-query -W openfoam14 > /opt/foam/openfoam14.version \
 && chmod -R a+rX /opt/foam /opt/AdditiveFOAM

COPY run-in-foam.sh /usr/local/bin/run-in-foam
ENTRYPOINT ["/usr/local/bin/run-in-foam"]

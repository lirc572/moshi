ARG CUDA_VERSION=12.4.1

FROM nvidia/cuda:${CUDA_VERSION}-devel-rockylinux9 as builder

ENV HOME=/root
ENV PATH="${HOME}/.local/bin:${PATH}"

RUN dnf -y update && \
    dnf -y --enablerepo=crb install git gcc gcc-c++ make cmake pkgconfig openssl-devel opus-devel && \
    dnf clean all

RUN mkdir -p /app /tmp

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable
ENV PATH="${HOME}/.cargo/bin:${PATH}"

COPY ./ /app/
WORKDIR /app/rust/

RUN cargo build --release --features cuda --bin moshi-backend

FROM nvidia/cuda:${CUDA_VERSION}-runtime-rockylinux9 as runner

RUN dnf -y update && \
    dnf -y --enablerepo=crb install opus-devel && \
    dnf clean all

RUN mkdir /conf

COPY --from=builder /app/rust/target/release/moshi-backend /bin/
COPY --from=builder /app/rust/moshi-backend/config.json /conf/
COPY --from=builder /app/rust/moshi-backend/config-q8.json /conf/

WORKDIR /root/

EXPOSE 8998

CMD ["/bin/moshi-backend", "--config", "/conf/config-q8.json", "standalone"]

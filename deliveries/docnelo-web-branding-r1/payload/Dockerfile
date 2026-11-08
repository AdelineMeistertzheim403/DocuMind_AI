ARG WEB_BASE_REF=documind-public-beta-web:r1-base-f15855942fb4
FROM ${WEB_BASE_REF}
USER root
RUN --network=none --mount=type=tmpfs,target=/etc rm -rf /app/dist
COPY --chown=node:node dist/ /app/dist/
USER node

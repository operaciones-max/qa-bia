# Imagen del servicio de extraccion. Construir desde la raiz del repo:
#   docker build -f backend/cmd/extraccion/Dockerfile -t qa-bia-extraccion .
#   docker run --rm -p 8081:8081 --env-file backend/.env qa-bia-extraccion

# MuPDF (go-fitz) necesita cgo: se compila con glibc y corre en una imagen con glibc.
FROM golang:1.24.7-bookworm AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY internal ./internal
COPY backend ./backend
RUN CGO_ENABLED=1 go build -trimpath -ldflags="-s -w" -o /extraccion ./backend/cmd/extraccion

FROM gcr.io/distroless/cc-debian12:nonroot
COPY --from=build /extraccion /extraccion
ENV EXTRACCION_PUERTO=8081
EXPOSE 8081
ENTRYPOINT ["/extraccion"]

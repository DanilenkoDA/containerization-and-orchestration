FROM golang:1.22
WORKDIR /src
COPY go.mod main.go ./
RUN go build -o /api .
EXPOSE 8080
CMD ["/api"]
package main

import (
	"context"
	"flag"
	"log/slog"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"returnsaiyan/gameserver/internal/domain/world"
	"returnsaiyan/gameserver/internal/repository/postgres"
	"returnsaiyan/gameserver/internal/session"
	"returnsaiyan/gameserver/internal/transport/tcp"
)

type serverHolder struct {
	server *tcp.Server
}

func (sh *serverHolder) GetConn(connID string) (*tcp.ClientConn, bool) {
	if sh.server != nil {
		return sh.server.GetConn(connID)
	}
	return nil, false
}

func main() {
	addr := flag.String("addr", "127.0.0.1:30001", "TCP listen address")
	dbURL := flag.String("db", "", "PostgreSQL DSN (falls back to DATABASE_URL env)")
	flag.Parse()

	logLevel := slog.LevelInfo
	if lvl := os.Getenv("LOG_LEVEL"); lvl != "" {
		switch strings.ToUpper(lvl) {
		case "DEBUG":
			logLevel = slog.LevelDebug
		case "WARN":
			logLevel = slog.LevelWarn
		case "ERROR":
			logLevel = slog.LevelError
		}
	}
	logger := slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{
		Level: logLevel,
	}))

	cfg := tcp.Config{
		Addr:           *addr,
		ReadTimeout:    30 * time.Second,
		WriteTimeout:   5 * time.Second,
		MaxConnections: 5000,
	}

	dsn := *dbURL
	if dsn == "" {
		dsn = os.Getenv("DATABASE_URL")
	}

	var auth session.Authenticator
	if dsn != "" {
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()

		logger.Info("connecting to PostgreSQL database...", slog.String("dsn", dsn))
		poolCfg := postgres.DefaultPoolConfig(dsn)
		pool, err := postgres.NewPool(ctx, poolCfg)
		if err != nil {
			logger.Error("failed to connect to PostgreSQL", slog.String("error", err.Error()))
			os.Exit(1)
		}
		defer pool.Close()

		migrator := postgres.NewMigrator(pool)
		if err := migrator.Up(ctx); err != nil {
			logger.Error("failed running database migrations", slog.String("error", err.Error()))
			os.Exit(1)
		}

		ver, _ := migrator.CurrentVersion(ctx)
		logger.Info("database schema up-to-date", slog.Int("version", ver))

		auth = postgres.NewPostgresAccountRepository(pool)
	} else {
		logger.Info("using in-memory local authenticator (no DATABASE_URL configured)")
		auth = session.NewLocalAuthenticator()
	}

	sessionMgr := session.NewSessionManager(30 * time.Minute)
	worldEngine := world.NewWorldEngine(100 * time.Millisecond)
	worldEngine.Start(context.Background())
	defer worldEngine.Stop()

	holder := &serverHolder{}

	handler := session.NewAuthHandler(auth, sessionMgr, holder, "127.0.0.1", 30001, logger)
	handler.SetWorldEngine(worldEngine)
	server := tcp.NewServer(cfg, handler, logger)
	holder.server = server

	if err := server.Start(); err != nil {
		logger.Error("failed to start TCP game server", slog.String("error", err.Error()))
		os.Exit(1)
	}

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, os.Interrupt, syscall.SIGTERM)
	<-sigCh

	logger.Info("shutdown signal received")
	if err := server.Stop(5 * time.Second); err != nil {
		logger.Error("error during server shutdown", slog.String("error", err.Error()))
	}
}

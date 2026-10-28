package postgres

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

var (
	ErrItemNotFound       = errors.New("inventory item not found in slot")
	ErrInsufficientCount  = errors.New("insufficient item count for transfer")
	ErrTargetSlotOccupied = errors.New("target inventory slot is already occupied")
)

// InventoryItem represents an item stack in a character inventory slot.
type InventoryItem struct {
	RoleID    int32     `json:"role_id"`
	Slot      int       `json:"slot"`
	ItemID    int       `json:"item_id"`
	Count     int       `json:"count"`
	UpdatedAt time.Time `json:"updated_at"`
}

// PostgresInventoryRepository handles character inventory persistence.
type PostgresInventoryRepository struct {
	pool *pgxpool.Pool
}

func NewPostgresInventoryRepository(pool *pgxpool.Pool) *PostgresInventoryRepository {
	return &PostgresInventoryRepository{pool: pool}
}

// SetItem inserts or updates an item stack in a specific slot.
func (r *PostgresInventoryRepository) SetItem(ctx context.Context, roleID int32, slot int, itemID int, count int) error {
	if count <= 0 {
		return errors.New("item count must be strictly positive")
	}

	query := `
	INSERT INTO player_inventories (role_id, slot, item_id, count, updated_at)
	VALUES ($1, $2, $3, $4, NOW())
	ON CONFLICT (role_id, slot) DO UPDATE SET
		item_id = EXCLUDED.item_id,
		count = EXCLUDED.count,
		updated_at = NOW();`

	_, err := r.pool.Exec(ctx, query, roleID, slot, itemID, count)
	if err != nil {
		return fmt.Errorf("failed to set inventory item: %w", err)
	}

	return nil
}

// GetItem retrieves the item in a specific inventory slot.
func (r *PostgresInventoryRepository) GetItem(ctx context.Context, roleID int32, slot int) (*InventoryItem, error) {
	query := `
	SELECT role_id, slot, item_id, count, updated_at
	FROM player_inventories
	WHERE role_id = $1 AND slot = $2;`

	var item InventoryItem
	err := r.pool.QueryRow(ctx, query, roleID, slot).Scan(
		&item.RoleID,
		&item.Slot,
		&item.ItemID,
		&item.Count,
		&item.UpdatedAt,
	)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, ErrItemNotFound
		}
		return nil, fmt.Errorf("failed to query inventory item: %w", err)
	}

	return &item, nil
}

// GetInventory retrieves all items for a role ordered by slot index.
func (r *PostgresInventoryRepository) GetInventory(ctx context.Context, roleID int32) ([]InventoryItem, error) {
	query := `
	SELECT role_id, slot, item_id, count, updated_at
	FROM player_inventories
	WHERE role_id = $1
	ORDER BY slot ASC;`

	rows, err := r.pool.Query(ctx, query, roleID)
	if err != nil {
		return nil, fmt.Errorf("failed to query inventory: %w", err)
	}
	defer rows.Close()

	var items []InventoryItem
	for rows.Next() {
		var item InventoryItem
		if err := rows.Scan(&item.RoleID, &item.Slot, &item.ItemID, &item.Count, &item.UpdatedAt); err != nil {
			return nil, fmt.Errorf("failed to scan inventory item: %w", err)
		}
		items = append(items, item)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("rows iteration error: %w", err)
	}

	return items, nil
}

// RemoveItem removes the item from a specific slot.
func (r *PostgresInventoryRepository) RemoveItem(ctx context.Context, roleID int32, slot int) error {
	query := `
	DELETE FROM player_inventories
	WHERE role_id = $1 AND slot = $2;`

	_, err := r.pool.Exec(ctx, query, roleID, slot)
	if err != nil {
		return fmt.Errorf("failed to remove inventory item: %w", err)
	}

	return nil
}

// TransferItem atomically moves or splits an item stack between two roles/slots in an explicit transaction.
// If the target slot is empty, the item is moved or created.
// If the target slot has the same item ID, the count is combined.
// If an error occurs, the entire transaction is rolled back.
func (r *PostgresInventoryRepository) TransferItem(
	ctx context.Context,
	fromRoleID int32,
	fromSlot int,
	toRoleID int32,
	toSlot int,
	transferCount int,
) error {
	if transferCount <= 0 {
		return errors.New("transfer count must be positive")
	}

	return WithTx(ctx, r.pool, pgx.TxOptions{IsoLevel: pgx.ReadCommitted}, func(tx pgx.Tx) error {
		// 1. Lock and read source item
		var sourceItemID int
		var sourceCount int
		err := tx.QueryRow(ctx, `
			SELECT item_id, count
			FROM player_inventories
			WHERE role_id = $1 AND slot = $2
			FOR UPDATE;`, fromRoleID, fromSlot).Scan(&sourceItemID, &sourceCount)
		if err != nil {
			if errors.Is(err, pgx.ErrNoRows) {
				return ErrItemNotFound
			}
			return fmt.Errorf("failed to lock source item: %w", err)
		}

		if sourceCount < transferCount {
			return fmt.Errorf("%w: requested %d, available %d", ErrInsufficientCount, transferCount, sourceCount)
		}

		// 2. Lock target item if it exists
		var targetItemID int
		var targetCount int
		targetExists := true
		err = tx.QueryRow(ctx, `
			SELECT item_id, count
			FROM player_inventories
			WHERE role_id = $1 AND slot = $2
			FOR UPDATE;`, toRoleID, toSlot).Scan(&targetItemID, &targetCount)
		if err != nil {
			if errors.Is(err, pgx.ErrNoRows) {
				targetExists = false
			} else {
				return fmt.Errorf("failed to lock target slot: %w", err)
			}
		}

		// 3. Update source slot
		if sourceCount == transferCount {
			// Delete source record if entire stack transferred
			_, err = tx.Exec(ctx, `
				DELETE FROM player_inventories
				WHERE role_id = $1 AND slot = $2;`, fromRoleID, fromSlot)
		} else {
			// Decrement count
			_, err = tx.Exec(ctx, `
				UPDATE player_inventories
				SET count = count - $1, updated_at = NOW()
				WHERE role_id = $2 AND slot = $3;`, transferCount, fromRoleID, fromSlot)
		}
		if err != nil {
			return fmt.Errorf("failed to deduct from source slot: %w", err)
		}

		// 4. Update or insert target slot
		if !targetExists {
			_, err = tx.Exec(ctx, `
				INSERT INTO player_inventories (role_id, slot, item_id, count, updated_at)
				VALUES ($1, $2, $3, $4, NOW());`, toRoleID, toSlot, sourceItemID, transferCount)
		} else {
			if targetItemID != sourceItemID {
				return fmt.Errorf("%w: target slot has item %d, cannot stack item %d", ErrTargetSlotOccupied, targetItemID, sourceItemID)
			}
			_, err = tx.Exec(ctx, `
				UPDATE player_inventories
				SET count = count + $1, updated_at = NOW()
				WHERE role_id = $2 AND slot = $3;`, transferCount, toRoleID, toSlot)
		}
		if err != nil {
			return fmt.Errorf("failed to credit target slot: %w", err)
		}

		return nil
	})
}

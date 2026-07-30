ALTER TABLE business_entity
    ADD COLUMN name_tr VARCHAR(160),
    ADD COLUMN description_tr TEXT;

ALTER TABLE entity_column
    ADD COLUMN business_name_tr VARCHAR(200),
    ADD COLUMN description_tr TEXT;

CREATE OR REPLACE FUNCTION reject_entity_structure_mutation() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE'
       OR NEW.entity_id IS DISTINCT FROM OLD.entity_id
       OR NEW.column_name IS DISTINCT FROM OLD.column_name
       OR NEW.business_name IS DISTINCT FROM OLD.business_name
       OR NEW.data_type IS DISTINCT FROM OLD.data_type
       OR NEW.description IS DISTINCT FROM OLD.description
       OR NEW.ordinal_position IS DISTINCT FROM OLD.ordinal_position THEN
        RAISE EXCEPTION 'an entity structure is immutable; register a new entity UUID';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

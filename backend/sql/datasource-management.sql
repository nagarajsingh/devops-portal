-- Optional manual DDL for environments where the portal DB user cannot CREATE TABLE.
-- The application normally creates these tables through SQLAlchemy on startup.

IF OBJECT_ID('weblogic_environment_instances', 'U') IS NULL
BEGIN
    CREATE TABLE weblogic_environment_instances (
        id INT IDENTITY(1,1) PRIMARY KEY,
        application VARCHAR(50) NOT NULL,
        environment VARCHAR(50) NOT NULL,
        instance_name VARCHAR(50) NOT NULL CONSTRAINT df_weblogic_instance_name DEFAULT 'app1',
        base_path VARCHAR(255) NULL,
        domain_name VARCHAR(100) NOT NULL,
        admin_host VARCHAR(255) NOT NULL,
        admin_port INT NOT NULL,
        ssh_port INT NOT NULL CONSTRAINT df_weblogic_ssh_port DEFAULT 22,
        wlst_path VARCHAR(500) NOT NULL,
        agent_pool VARCHAR(100) NOT NULL,
        default_db_host VARCHAR(255) NOT NULL,
        default_db_port INT NOT NULL,
        default_ons_nodes VARCHAR(1000) NULL,
        is_production BIT NOT NULL CONSTRAINT df_weblogic_is_production DEFAULT 0,
        is_active BIT NOT NULL CONSTRAINT df_weblogic_is_active DEFAULT 1,
        created_at DATETIME2 NOT NULL CONSTRAINT df_weblogic_created_at DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2 NOT NULL CONSTRAINT df_weblogic_updated_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT uq_weblogic_environment_instance UNIQUE(application, environment, instance_name)
    );
END;
GO

IF OBJECT_ID('weblogic_credentials', 'U') IS NULL
BEGIN
    CREATE TABLE weblogic_credentials (
        id INT IDENTITY(1,1) PRIMARY KEY,
        environment_instance_id INT NOT NULL,
        credential_type VARCHAR(50) NOT NULL,
        username VARCHAR(255) NOT NULL,
        password_ciphertext VARCHAR(MAX) NOT NULL,
        created_at DATETIME2 NOT NULL CONSTRAINT df_weblogic_credential_created DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2 NOT NULL CONSTRAINT df_weblogic_credential_updated DEFAULT SYSUTCDATETIME(),
        CONSTRAINT fk_weblogic_credential_environment
            FOREIGN KEY(environment_instance_id) REFERENCES weblogic_environment_instances(id),
        CONSTRAINT uq_weblogic_environment_credential UNIQUE(environment_instance_id, credential_type)
    );
END;
GO

IF OBJECT_ID('datasource_entity_profiles', 'U') IS NULL
BEGIN
    CREATE TABLE datasource_entity_profiles (
        id INT IDENTITY(1,1) PRIMARY KEY,
        environment_instance_id INT NOT NULL,
        entity_code VARCHAR(30) NOT NULL,
        service_id VARCHAR(100) NOT NULL,
        db_host VARCHAR(255) NOT NULL,
        db_port INT NOT NULL,
        ons_nodes VARCHAR(1000) NULL,
        password_pattern_ciphertext VARCHAR(MAX) NOT NULL,
        created_at DATETIME2 NOT NULL CONSTRAINT df_ds_entity_created DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2 NOT NULL CONSTRAINT df_ds_entity_updated DEFAULT SYSUTCDATETIME(),
        CONSTRAINT fk_ds_entity_environment
            FOREIGN KEY(environment_instance_id) REFERENCES weblogic_environment_instances(id),
        CONSTRAINT uq_datasource_entity_profile UNIQUE(environment_instance_id, entity_code)
    );
END;
GO

IF OBJECT_ID('datasource_operations', 'U') IS NULL
BEGIN
    CREATE TABLE datasource_operations (
        id INT IDENTITY(1,1) PRIMARY KEY,
        request_id VARCHAR(40) NULL,
        environment_instance_id INT NOT NULL,
        reference_entity VARCHAR(30) NOT NULL,
        target_entity VARCHAR(30) NOT NULL,
        datasource_type VARCHAR(30) NOT NULL,
        db_host VARCHAR(255) NOT NULL,
        db_port INT NOT NULL,
        service_id VARCHAR(100) NOT NULL,
        ons_nodes VARCHAR(1000) NULL,
        password_pattern_ciphertext VARCHAR(MAX) NOT NULL,
        status VARCHAR(50) NOT NULL,
        requested_by VARCHAR(255) NOT NULL,
        azure_pipeline_id INT NULL,
        azure_run_id INT NULL,
        azure_run_url VARCHAR(1000) NULL,
        preview_json VARCHAR(MAX) NULL,
        result_message VARCHAR(MAX) NULL,
        created_at DATETIME2 NOT NULL CONSTRAINT df_ds_operation_created DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2 NOT NULL CONSTRAINT df_ds_operation_updated DEFAULT SYSUTCDATETIME(),
        completed_at DATETIME2 NULL,
        CONSTRAINT fk_ds_operation_environment
            FOREIGN KEY(environment_instance_id) REFERENCES weblogic_environment_instances(id),
        CONSTRAINT uq_ds_operation_request UNIQUE(request_id)
    );
END;
GO

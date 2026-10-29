create table if not exists usuarios(
  id serial primary key,
  usuario text unique not null,
  nombre text not null,
  rol text not null check (rol in ('admin','medico','secretaria','fisio')),
  password_hash text not null,
  activo boolean not null default true);
create table if not exists pacientes(
  id serial primary key,
  nombre text not null, edad int, cedula text, seguro text,
  alergias text, diagnostico text,
  etapa int not null default 0,
  creado_en timestamptz not null default now());
create table if not exists citas(
  id serial primary key,
  paciente_id int not null references pacientes(id) on delete cascade,
  fecha date not null, hora time, motivo text);
create table if not exists evaluaciones(
  id serial primary key,
  paciente_id int not null references pacientes(id) on delete cascade,
  fecha date not null default current_date, texto text not null);
create table if not exists estudios_imagenes(
  id serial primary key,
  paciente_id int not null references pacientes(id) on delete cascade,
  fecha date not null default current_date, tipo text, estado text default 'Por revisar', informe text);
create table if not exists cirugias(
  id serial primary key,
  paciente_id int not null references pacientes(id) on delete cascade,
  fecha date, procedimiento text not null, estado text default 'Programada');
create table if not exists implantes(
  id serial primary key,
  cirugia_id int references cirugias(id) on delete cascade,
  paciente_id int not null references pacientes(id) on delete cascade,
  descripcion text, lote text);
create table if not exists pt_sesiones(
  id serial primary key,
  paciente_id int not null references pacientes(id) on delete cascade,
  fecha date not null default current_date, descripcion text, dolor int check (dolor between 0 and 10));
create table if not exists formularios_proms(
  id serial primary key,
  paciente_id int not null references pacientes(id) on delete cascade,
  fecha date not null default current_date, cuestionario text, puntaje int);
create table if not exists referimientos(
  id serial primary key,
  paciente_id int not null references pacientes(id) on delete cascade,
  fecha date not null default current_date, detalle text, estado text default 'Pendiente');
create table if not exists autorizaciones_preauth(
  id serial primary key,
  paciente_id int not null references pacientes(id) on delete cascade,
  procedimiento text, seguro text, estado text default 'Por solicitar', vence date);
create table if not exists cargos_facturacion(
  id serial primary key,
  paciente_id int not null references pacientes(id) on delete cascade,
  fecha date not null default current_date, codigo text, concepto text,
  monto numeric(12,2) not null default 0, estado text default 'Pendiente');
create table if not exists documentos(
  id serial primary key,
  paciente_id int not null references pacientes(id) on delete cascade,
  nombre text not null, url text);
create table if not exists auditoria(
  id bigserial primary key,
  usuario text not null, accion text not null, tabla text, registro_id int,
  fecha timestamptz not null default now());
create index if not exists ix_pac_nombre on pacientes(lower(nombre));
create index if not exists ix_pac_cedula on pacientes(cedula);
create index if not exists ix_citas_fecha on citas(fecha);
create index if not exists ix_aud_fecha on auditoria(fecha);
create table if not exists funciones_rol(
  rol text not null, modulo text not null, primary key (rol, modulo));
alter table pacientes add column if not exists antecedentes_morbidos text;
alter table pacientes add column if not exists antecedentes_quirurgicos text;
alter table pacientes add column if not exists medicamentos text;
alter table pacientes add column if not exists antecedentes_familiares text;
alter table pacientes add column if not exists habitos text;
alter table pacientes add column if not exists fecha_nacimiento date;
alter table pacientes add column if not exists sexo text;
alter table pacientes add column if not exists telefono text;
alter table pacientes add column if not exists correo text;
alter table pacientes add column if not exists direccion text;
alter table pacientes add column if not exists numero_afiliado text;
alter table pacientes add column if not exists tipo_sangre text;
alter table cargos_facturacion add column if not exists medico text;
create table if not exists tarifario(
  id serial primary key,
  codigo text, nombre text not null, fuente text,
  precio numeric(12,2) not null default 0);
alter table tarifario add column if not exists categoria text;
create table if not exists procedimientos_paciente(
  id serial primary key,
  paciente_id int not null references pacientes(id) on delete cascade,
  fecha date not null default current_date, procedimiento text not null,
  codigo text, categoria text, precio numeric(12,2) not null default 0,
  medico text, estado text default 'Indicado');
create table if not exists imagenes_estudio(
  id serial primary key,
  estudio_id int not null references estudios_imagenes(id) on delete cascade,
  mime text not null, datos bytea not null,
  creado_en timestamptz not null default now());
alter table evaluaciones add column if not exists verificado_por text;
alter table evaluaciones add column if not exists verificado_en timestamptz;
alter table estudios_imagenes add column if not exists verificado_por text;
alter table estudios_imagenes add column if not exists verificado_en timestamptz;
alter table cirugias add column if not exists verificado_por text;
alter table cirugias add column if not exists verificado_en timestamptz;
alter table pt_sesiones add column if not exists verificado_por text;
alter table pt_sesiones add column if not exists verificado_en timestamptz;
alter table formularios_proms add column if not exists verificado_por text;
alter table formularios_proms add column if not exists verificado_en timestamptz;
alter table referimientos add column if not exists verificado_por text;
alter table referimientos add column if not exists verificado_en timestamptz;
alter table autorizaciones_preauth add column if not exists verificado_por text;
alter table autorizaciones_preauth add column if not exists verificado_en timestamptz;
alter table procedimientos_paciente add column if not exists verificado_por text;
alter table procedimientos_paciente add column if not exists verificado_en timestamptz;
alter table cargos_facturacion add column if not exists verificado_por text;
alter table cargos_facturacion add column if not exists verificado_en timestamptz;
alter table documentos add column if not exists verificado_por text;
alter table documentos add column if not exists verificado_en timestamptz;
alter table documentos add column if not exists tipo text;
alter table documentos add column if not exists fecha date default current_date;
alter table documentos add column if not exists archivo bytea;
alter table documentos add column if not exists mime text;
alter table documentos add column if not exists tamano int;

// ============================================================
// ATLAS BRASIL — MOCK Neo4j
// Investigações BETA / Lava Jato (INQ 3989 + desmembramentos)
//
// DEMO apenas. Não interpretar INVESTIGATED/CHARGED como condenação.
// Preferir CaseParticipation temporal no produto definitivo
// (ver data/mocks/investigacoes_beta_lava_jato.json).
// ============================================================

CREATE CONSTRAINT person_id IF NOT EXISTS
FOR (n:Person) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT case_id IF NOT EXISTS
FOR (n:LegalCase) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT org_id IF NOT EXISTS
FOR (n:Organization) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT party_id IF NOT EXISTS
FOR (n:Party) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT operation_id IF NOT EXISTS
FOR (n:InvestigationOperation) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT participation_id IF NOT EXISTS
FOR (n:CaseParticipation) REQUIRE n.id IS UNIQUE;

MERGE (lava:InvestigationOperation {id: 'operation_lava_jato'})
SET lava.name = 'Operação Lava Jato',
    lava.started_at = date('2014-03-17'),
    lava.demo = true;

MERGE (stf:Organization {id:'org_stf'}) SET stf.name='Supremo Tribunal Federal', stf.type='COURT';
MERGE (pgr:Organization {id:'org_pgr'}) SET pgr.name='Procuradoria-Geral da República', pgr.type='PROSECUTION';
MERGE (mpf:Organization {id:'org_mpf'}) SET mpf.name='Ministério Público Federal', mpf.type='PROSECUTION';
MERGE (pf:Organization {id:'org_pf'}) SET pf.name='Polícia Federal', pf.type='POLICE';

MERGE (:Party {id:'party_pt', name:'Partido dos Trabalhadores', abbreviation:'PT'});
MERGE (:Party {id:'party_pp', name:'Progressistas', abbreviation:'PP'});
MERGE (:Party {id:'party_pmdb', name:'PMDB/MDB', abbreviation:'PMDB/MDB'});

MERGE (inq3989:LegalCase {id:'stf_inq_3989', number:'INQ 3989'});
MERGE (inq4325:LegalCase {id:'stf_inq_4325', number:'INQ 4325', nucleus:'PT'});
MERGE (inq4326:LegalCase {id:'stf_inq_4326', number:'INQ 4326', nucleus:'PMDB_SENADO'});
MERGE (inq4327:LegalCase {id:'stf_inq_4327', number:'INQ 4327', nucleus:'PMDB_CAMARA'});
MERGE (inq4631:LegalCase {id:'stf_inq_4631', number:'INQ 4631', nucleus:'PP'});

MATCH (lava:InvestigationOperation {id:'operation_lava_jato'}), (i:LegalCase {id:'stf_inq_3989'})
MERGE (lava)-[:HAS_CASE]->(i);

MATCH (parent:LegalCase {id:'stf_inq_3989'}), (child:LegalCase)
WHERE child.id IN ['stf_inq_4325','stf_inq_4326','stf_inq_4327','stf_inq_4631']
MERGE (parent)-[:SPLIT_INTO {at:'2016', by:'Teori Zavascki'}]->(child);

MERGE (teori:Person {id:'person_teori_zavascki'}) SET teori.name='Teori Zavascki';
MERGE (fachin:Person {id:'person_edson_fachin'}) SET fachin.name='Edson Fachin';
MERGE (janot:Person {id:'person_rodrigo_janot'}) SET janot.name='Rodrigo Janot';

MATCH (teori:Person {id:'person_teori_zavascki'}), (fachin:Person {id:'person_edson_fachin'})
MATCH (c:LegalCase)
WHERE c.id IN ['stf_inq_3989','stf_inq_4325','stf_inq_4326','stf_inq_4327']
MERGE (teori)-[:RELATOR_OF {valid_to:'2017-01'}]->(c)
MERGE (fachin)-[:RELATOR_OF {valid_from:'2017-02'}]->(c);

MATCH (janot:Person {id:'person_rodrigo_janot'}), (pgr:Organization {id:'org_pgr'})
MERGE (janot)-[:HELD_OFFICE {office:'Procurador-Geral da República', demo:true}]->(pgr);

// Institutions — papéis corretos (sem Moro→político)
MATCH (pf:Organization {id:'org_pf'}), (pgr:Organization {id:'org_pgr'}), (stf:Organization {id:'org_stf'})
MATCH (c:LegalCase)
WHERE c.id IN ['stf_inq_3989','stf_inq_4325','stf_inq_4326','stf_inq_4327','stf_inq_4631']
MERGE (pf)-[:PERFORMED_DILIGENCE]->(c)
MERGE (pgr)-[:PROSECUTION_AUTHORITY_FOR]->(c)
MERGE (c)-[:PROCESSED_BY]->(stf);

// Exemplo temporal CaseParticipation (Gleisi / INQ 4325)
MERGE (gleisi:Person {id:'p_cam_107283'}) SET gleisi.name='Gleisi Hoffmann';
MERGE (cp1:CaseParticipation {id:'cp_gleisi_4325_inv'})
SET cp1.status='INVESTIGATED', cp1.valid_from='2016';
MERGE (cp2:CaseParticipation {id:'cp_gleisi_4325_chg'})
SET cp2.status='CHARGED', cp2.valid_from='2017-09';
MERGE (cp3:CaseParticipation {id:'cp_gleisi_4325_rej'})
SET cp3.status='CHARGE_REJECTED', cp3.valid_from='2023-06',
    cp3.note='STF rejeitou denúncia remanescente; falta de justa causa';

MATCH (g:Person {id:'p_cam_107283'}), (c:LegalCase {id:'stf_inq_4325'})
MATCH (cp1:CaseParticipation {id:'cp_gleisi_4325_inv'})
MATCH (cp2:CaseParticipation {id:'cp_gleisi_4325_chg'})
MATCH (cp3:CaseParticipation {id:'cp_gleisi_4325_rej'})
MERGE (g)-[:HAS_PARTICIPATION]->(cp1)-[:IN_CASE]->(c)
MERGE (g)-[:HAS_PARTICIPATION]->(cp2)-[:IN_CASE]->(c)
MERGE (g)-[:HAS_PARTICIPATION]->(cp3)-[:IN_CASE]->(c);

// Temer — mudança de jurisdição
MERGE (temer:Person {id:'p_cam_73552'}) SET temer.name='Michel Temer';
MERGE (cpt:CaseParticipation {id:'cp_temer_4327_j'})
SET cpt.status='JURISDICTION_CHANGED', cpt.valid_from='2019-01',
    cpt.note='Fim do mandato — competência STF cessa';
MATCH (t:Person {id:'p_cam_73552'}), (c:LegalCase {id:'stf_inq_4327'}),
      (cpt:CaseParticipation {id:'cp_temer_4327_j'})
MERGE (t)-[:HAS_PARTICIPATION]->(cpt)-[:IN_CASE]->(c);

// Dataset completo de pessoas/participações: carregar via JSON
// data/mocks/investigacoes_beta_lava_jato.json (122 participações).

export type VentureSector = "ai" | "autonomy" | "climate_energy" | "consumer" | "defense" | "enterprise_software" | "fintech" | "semiconductors" | "space";
export type VentureStage = "pre_seed_seed" | "early" | "growth" | "undisclosed";
export type VentureRole = "lead" | "participant" | "undisclosed";
export type VentureFollowOn = "yes" | "no" | "undisclosed";

export type VentureRelationship = {
  company_id: string;
  company_name: string;
  sector: VentureSector;
  first_partnered_year: number | null;
  stage: VentureStage;
  participation_role: VentureRole;
  follow_on_status: VentureFollowOn;
  source_url: string;
  source_sha256: string;
};

export type VentureFirm = {
  firm_id: string;
  name: string;
  category: "core_technology_ai";
  strategy_labels: string[];
  source_url: string;
  source_sha256: string;
  tracked_relationship_count: number;
  sector_counts: Array<{ sector: VentureSector; company_count: number }>;
  relationships: VentureRelationship[];
};

export type VentureCatalog = {
  schema_version: "vc-catalog.v1";
  release_id: string;
  manifest_hash: string;
  source_manifest_hash: string;
  observed_at: string;
  source_fresh_through: string;
  scope: string;
  methodology: string;
  limitations: string[];
  firms: VentureFirm[];
};

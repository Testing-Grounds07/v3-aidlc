export type Identifier = string;

export interface EntityReference {
  readonly id: Identifier;
  readonly version: number;
}

// Milestone 1 supplies governed entities and transition rules.

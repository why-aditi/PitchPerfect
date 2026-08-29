// Mirrors the Knowledge model in backend/models.py. The demo site only ever renders
// pricing — everything else about an agent lives in the console.

export type Tier = {
  name: string;
  per_seat_month: number;
  min_seats: number;
  max_seats: number | null;
  volume_break: { seats: number; per_seat_month: number } | null;
  features: string[];
};

export type Pricing = {
  currency: string;
  tiers: Tier[];
};

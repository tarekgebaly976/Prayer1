export type UUID = string;

export interface PlantAccess {
  plant_id: UUID; plant_code: string; plant_name: string; timezone: string; currency: string;
  role: string; department_id: UUID | null; permissions: string[];
}
export interface Me { id: UUID; email: string; full_name: string; locale: string; is_system_admin: boolean; plants: PlantAccess[]; csrf_token: string }
export interface Page<T> { items: T[]; total: number; limit: number; offset: number }

export interface Department { id: UUID; code: string; name: string; name_ar: string | null; type: string; is_active: boolean }
export interface Asset {
  id: UUID; code: string; name: string; name_ar: string | null; department_id: UUID; parent_id: UUID | null; level: string; path: string;
  description: string | null; oem: string | null; model: string | null; serial_number: string | null; install_date: string | null;
  criticality: "A" | "B" | "C"; status: string; location: string | null; equipment_type: string | null; specifications: Record<string, unknown>;
  operating_limits: Record<string, unknown>; operating_hours: number; qr_token: string; is_active: boolean; created_at: string;
}
export interface AssetNode { id: UUID; code: string; name: string; level: string; parent_id: UUID | null; department_id: UUID; criticality: string; status: string; child_count: number }

export interface WorkOrder {
  id: UUID; number: string; type: string; status: string; priority: string; asset_id: UUID; department_id: UUID; title: string;
  description: string | null; symptoms: string | null; symptom_code_id: UUID | null; problem_code_id: UUID | null; cause_code_id: UUID | null; remedy_code_id: UUID | null;
  supervisor_id: UUID | null; due_date: string | null; planned_start: string | null; planned_end: string | null; actual_start: string | null;
  actual_end: string | null; completed_at: string | null; closed_at: string | null; estimated_hours: number | null; estimated_cost: number | null;
  actual_labor_hours: number; actual_labor_cost: number; actual_material_cost: number; actual_service_cost: number; actual_cost: number;
  currency: string; downtime_hours: number | null; production_impact: string | null; production_loss_tons: number | null;
  requires_loto: boolean; requires_permit: boolean; permit_reference: string | null; safety_requirements: string | null;
  permit_types: string | null; permit_valid_until: string | null;
  source: string; external_ref: string | null;
  safety_signed_by_id: UUID | null; safety_signed_at: string | null; requires_testing: boolean; test_result: string | null;
  test_passed: boolean | null; tested_at: string | null; findings: string | null; recommendations: string | null; root_cause: string | null;
  corrective_action: string | null; is_repeat_failure: boolean; pm_occurrence_id: UUID | null; condition_alert_id: UUID | null;
  shutdown_package_id: UUID | null; work_request_id: UUID | null; version: number; created_at: string;
  assignments: { user_id: UUID; is_lead: boolean }[];
}
export interface ChecklistItem { id: UUID; seq: number; description: string; kind: "check" | "reading"; is_required: boolean; unit: string | null;
  min_value: number | null; max_value: number | null; is_done: boolean; is_ok: boolean | null; reading_value: number | null; remark: string | null; done_by: string | null }
export interface WODetail {
  work_order: WorkOrder; asset: { id: UUID; code: string; name: string; location: string | null; criticality: string } | null;
  allowed_transitions: string[]; assignees: { user_id: UUID; name: string; is_lead: boolean }[]; checklist: ChecklistItem[];
  labor: { id: UUID; name: string; work_date: string; hours: number; is_overtime: boolean; cost: number; notes: string | null }[];
  services: { id: UUID; description: string; cost: number; po_reference: string | null }[];
  reservations: { id: UUID; part_id: UUID; part_code: string; description: string; warehouse: string; warehouse_id: UUID; quantity: number; qty_issued: number; status: string; uom: string }[];
  transactions: { id: UUID; part_code: string; type: string; quantity: number; unit_cost: number; total_cost: number; at: string }[];
  parts_used: PartUsed[];
  loto: LotoPoint[];
  history: { from: string | null; to: string; by: string; at: string; comment: string | null }[];
  comments: { id: UUID; user: string; body: string; at: string }[];
  lube_tasks: { id: UUID; point_code: string; component: string | null; location: string | null; lubricant: string | null; lubricant_id: UUID;
    quantity: number; unit: string; method: string | null; status: string; quantity_actual: number | null; due_date: string }[];
  safety_signed_by: string | null; tested_by: string | null;
}
export interface Member { user: { id: UUID; email: string; full_name: string; trade: string | null; is_active: boolean; hourly_rate: number | null; employee_no: string | null; locale: string }; role_code: string; department_id: UUID | null; is_active: boolean }
export interface FailureCode { id: UUID; kind: "symptom" | "problem" | "cause" | "remedy"; code: string; description: string; equipment_type: string | null; category: string | null; suggested: boolean }
export interface KPI { code: string; value: number | null; unit: string; available: boolean; reason: string | null; numerator: number | null; denominator: number | null; details: Record<string, unknown>; records?: Record<string, unknown>[] }
export interface Notification { id: UUID; kind: string; severity: string; title: string; body: string | null; link: string | null; created_at: string; read_at: string | null }
export interface Part { id: UUID; code: string; description: string; oem_part_number: string | null; manufacturer: string | null; uom: string; criticality: string;
  is_critical_spare: boolean; min_qty: number; max_qty: number; reorder_point: number; safety_stock: number; average_cost: number; unit_price: number; currency: string;
  qty_on_hand?: number; qty_reserved?: number; qty_available?: number; qty_on_order?: number; is_obsolete: boolean; lead_time_days: number | null }
export interface Warehouse { id: UUID; code: string; name: string }

export interface PartUsed {
  id: UUID; used_on: string; work_order_id: UUID; work_order: string; wo_title: string; wo_type: string; asset_id: UUID; asset_code: string;
  asset_name: string; part_id: UUID | null; part_code: string | null; description: string; quantity: number; uom: string; unit_cost: number;
  total_cost: number; note: string | null;
}

export interface LotoPoint {
  id: UUID; point: string; energy_type: string; lock_number: string | null; zero_energy_verified: boolean; applied_by: string | null;
  applied_at: string; removed_by: string | null; removed_at: string | null;
}

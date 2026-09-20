# Data Contract

## Required Fields

All modules must use these exact field names:

- shipper
- consignee
- notify_party
- port_of_loading
- port_of_discharge
- container_count
- gross_weight_kg


## 1. Classifier Output

```json
{
  "email_id": "001",
  "category": "document_comparison",
  "should_compare": true,
  "attachments": {
    "si": "path/to/si.txt",
    "bl": "path/to/bl.txt"
  }
}



{
  "email_id": "001",
  "si": {
    "shipper": "ABC Trading",
    "consignee": "XYZ Logistics",
    "notify_party": "DEF Shipping",
    "port_of_loading": "Port Klang",
    "port_of_discharge": "Singapore",
    "container_count": 3,
    "gross_weight_kg": 22000
  },
  "bl": {
    "shipper": "ABC Trading",
    "consignee": "XYZ Logistics",
    "notify_party": "DEF Shipping",
    "port_of_loading": "Port Klang",
    "port_of_discharge": "Singapore",
    "container_count": 4,
    "gross_weight_kg": 22000
  }
}


{
  "email_id": "001",
  "status": "mismatch_detected",
  "mismatches": [
    {
      "field": "container_count",
      "si": 3,
      "bl": 4
    }
  ],
  "review_required": false,
  "review_reason": null
}

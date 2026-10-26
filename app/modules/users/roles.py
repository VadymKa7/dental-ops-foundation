"""Role names stored on users.

Patients are records without a password. Staff roles can sign in.
"""

PATIENT = "patient"
ADMIN = "admin"
DOCTOR = "doctor"
RECEPTION = "reception"
STAFF_ROLES = frozenset({ADMIN, DOCTOR, RECEPTION})
ALL_ROLES = STAFF_ROLES | {PATIENT}

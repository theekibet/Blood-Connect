# blood/utils/blood_compatibility.py
# returns the list of donor blood types that are compatible
def get_compatible_blood_types(blood_type):
    """
    Return a list of compatible blood types for transfusion based on the recipient's blood type.
    """
    compatibility = {
        "O-": ["O-"],
        "O+": ["O-", "O+"],
        "A-": ["O-", "A-"],
        "A+": ["O-", "O+", "A-", "A+"],
        "B-": ["O-", "B-"],
        "B+": ["O-", "O+", "B-", "B+"],
        "AB-": ["O-", "A-", "B-", "AB-"],
        "AB+": ["O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"],
    }
    return compatibility.get(blood_type, [blood_type])
#returns a list of patient blood types compatible as recipients
def get_compatible_recipient_blood_types(donor_blood_type):
    """
    Return a list of recipient blood types compatible with donor blood type.
    """
    compatibility = {
        "O-": ["O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"],  # universal donor
        "O+": ["O+", "A+", "B+", "AB+"],
        "A-": ["A-", "A+", "AB-", "AB+"],
        "A+": ["A+", "AB+"],
        "B-": ["B-", "B+", "AB-", "AB+"],
        "B+": ["B+", "AB+"],
        "AB-": ["AB-", "AB+"],
        "AB+": ["AB+"],
    }
    return compatibility.get(donor_blood_type, [])
import pandas as pd
from core.connection import get_sheet
from utils import safe_int

def get_master_df():
    # Fetch and sort in one go
    data = get_sheet("Employee_Master").get_all_records()
    df = pd.DataFrame(data)
    if "RankID" in df.columns:
        df["RankID_Int"] = df["RankID"].apply(lambda x: safe_int(x, 999))
        df = df.sort_values("RankID_Int")
    return df

def get_attendees_for_meeting(mid):
    # Filtering logic belongs here, not in the UI
    all_att = pd.DataFrame(get_sheet("Meeting_Attendees").get_all_records())
    subset = all_att[all_att["MeetingID"].astype(str) == str(mid)]
    # Apply sorting immediately
    return subset.sort_values("RankID") if "RankID" in subset.columns else subset

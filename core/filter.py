def filter_job_by_title(title, config_filters):
    title_lower = title.lower()
    exclude_keywords = config_filters.get('exclude_title_keywords', [])
    include_keywords = config_filters.get('include_title_keywords', [])
    
    for ex_word in exclude_keywords:
        if ex_word in title_lower:
            return False, "excluded_explicit", ex_word
            
    if not include_keywords:
        return True, "included", None
        
    for inc_word in include_keywords:
        if inc_word in title_lower:
            return True, "included", inc_word
            
    return False, "excluded_implicit", None

def merge_processed_titles(global_dict, local_dict):
    for key in global_dict:
        global_dict[key].extend(local_dict.get(key, []))
def solve_quiz_entrypoint(email:str,secret:str,start_url:str, max_second:int = 100):

    return {"email":email,
            "secret":secret,
            "start_url":start_url,
            "max_second":max_second
            }
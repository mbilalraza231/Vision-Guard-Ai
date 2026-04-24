import { useLocation, Link } from "react-router-dom";
import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Camera, Home } from "lucide-react";

const NotFound = () => {
  const location = useLocation();

  useEffect(() => {
    console.error(
      "404 Error: User attempted to access non-existent route:",
      location.pathname
    );
  }, [location.pathname]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="text-center">
        <div className="flex h-16 w-16 items-center justify-center rounded-xl bg-primary/10 mx-auto mb-6">
          <Camera className="h-8 w-8 text-primary" />
        </div>
        <h1 className="text-6xl font-bold mb-4">404</h1>
        <p className="text-xl text-muted-foreground mb-8">
          The page you're looking for doesn't exist
        </p>
        <Link to="/dashboard">
          <Button className="gap-2">
            <Home className="h-4 w-4" />
            Return to Dashboard
          </Button>
        </Link>
      </div>
    </div>
  );
};

export default NotFound;
